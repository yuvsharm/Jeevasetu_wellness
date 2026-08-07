from datetime import date, timedelta

import pytest
from django.contrib.auth.hashers import check_password
from django.urls import reverse
from django.utils import timezone

from apps.appointments.models import (
    Appointment,
    VisitVerification,
    VisitVerificationAuditEvent,
)
from apps.appointments.scheduling import (
    assign_physiotherapist,
    cancel_appointment,
    reschedule_appointment,
)
from apps.appointments.visit_verification import can_start_visit
from apps.staff.models import StaffProfile
from tests.test_appointment_operations import create_scheduled
from tests.test_scheduling import add_actor, headers, setup_domain, start_at

pytestmark = pytest.mark.django_db


def ready_appointment(api_client, slug):
    values = setup_domain(slug)
    appointment = create_scheduled(api_client, values)
    Appointment.objects.filter(pk=appointment.pk).update(
        status=Appointment.Status.CONFIRMED,
        assignment_status=Appointment.AssignmentStatus.ACCEPTED,
        scheduled_start=timezone.now(),
        scheduled_end=timezone.now() + timedelta(hours=1),
    )
    appointment.refresh_from_db()
    return values, appointment


def issue(api_client, values, appointment):
    organization, _, _, _, _, _, customer, *_ = values
    api_client.force_authenticate(customer)
    response = api_client.post(
        reverse("schedule-customer-visit-verification", args=[appointment.id]),
        {},
        format="json",
        **headers(organization),
    )
    return response


def verify(api_client, values, appointment, otp):
    organization, _, _, _, physiotherapist, *_ = values
    api_client.force_authenticate(physiotherapist)
    return api_client.post(
        reverse("schedule-physiotherapist-visit-verification", args=[appointment.id]),
        {"otp": otp},
        format="json",
        **headers(organization),
    )


def test_secure_otp_is_hashed_issued_once_and_correct_value_verifies(api_client):
    values, appointment = ready_appointment(api_client, "visit-success")
    issued = issue(api_client, values, appointment)
    assert issued.status_code == 201
    otp = issued.data["otp"]
    assert len(otp) == 6 and otp.isdigit()
    verification = VisitVerification.objects.get(appointment=appointment)
    assert verification.otp_hash != otp
    assert check_password(otp, verification.otp_hash)
    assert otp not in str(verification.__dict__)

    response = verify(api_client, values, appointment, otp)
    verification.refresh_from_db()
    assert response.status_code == 200
    assert verification.state == VisitVerification.State.VERIFIED
    assert can_start_visit(appointment)
    assert not verification.audit_events.filter(reason_code__contains=otp).exists()


def test_wrong_otp_increments_attempts_and_locks_at_maximum(api_client):
    values, appointment = ready_appointment(api_client, "visit-lock")
    issue(api_client, values, appointment)
    for attempt in range(5):
        response = verify(api_client, values, appointment, "000000")
        assert response.status_code == 400
        verification = VisitVerification.objects.get(appointment=appointment)
        assert verification.failed_attempt_count == attempt + 1
    assert verification.state == VisitVerification.State.LOCKED
    assert verification.locked_at is not None
    assert verification.audit_events.filter(event=VisitVerificationAuditEvent.Event.LOCKED).exists()


def test_expired_and_used_otp_are_rejected(api_client):
    values, appointment = ready_appointment(api_client, "visit-expired")
    issued = issue(api_client, values, appointment)
    verification = VisitVerification.objects.get(appointment=appointment)
    verification.expires_at = timezone.now() - timedelta(seconds=1)
    verification.save(update_fields=("expires_at",))
    expired = verify(api_client, values, appointment, issued.data["otp"])
    verification.refresh_from_db()
    assert expired.status_code == 400
    assert verification.state == VisitVerification.State.EXPIRED

    values, appointment = ready_appointment(api_client, "visit-reused")
    issued = issue(api_client, values, appointment)
    assert verify(api_client, values, appointment, issued.data["otp"]).status_code == 200
    assert verify(api_client, values, appointment, issued.data["otp"]).status_code == 400


@pytest.mark.parametrize(
    ("slug", "status", "assignment_status", "remove_physio"),
    [
        ("visit-state", Appointment.Status.SCHEDULED, Appointment.AssignmentStatus.ACCEPTED, False),
        (
            "visit-no-physio",
            Appointment.Status.CONFIRMED,
            Appointment.AssignmentStatus.UNASSIGNED,
            True,
        ),
        (
            "visit-pending",
            Appointment.Status.CONFIRMED,
            Appointment.AssignmentStatus.PENDING,
            False,
        ),
    ],
)
def test_unapproved_unassigned_or_unaccepted_appointment_cannot_issue_otp(
    api_client, slug, status, assignment_status, remove_physio
):
    values, appointment = ready_appointment(api_client, slug)
    appointment.status = status
    appointment.assignment_status = assignment_status
    if remove_physio:
        appointment.physiotherapist = None
    appointment.save(update_fields=("status", "assignment_status", "physiotherapist"))
    assert issue(api_client, values, appointment).status_code == 400
    assert not VisitVerification.objects.filter(appointment=appointment).exists()


def test_start_policy_requires_successful_arrival_verification(api_client):
    values, appointment = ready_appointment(api_client, "visit-start-policy")
    assert not can_start_visit(appointment)
    issued = issue(api_client, values, appointment)
    assert verify(api_client, values, appointment, issued.data["otp"]).status_code == 200
    appointment.refresh_from_db()
    assert can_start_visit(appointment)


def test_customer_scope_and_staff_responses_never_expose_otp(api_client):
    values, appointment = ready_appointment(api_client, "visit-permissions")
    organization, _, owner, manager, physiotherapist, _, customer, *_ = values
    issued = issue(api_client, values, appointment)
    otp = issued.data["otp"]

    for actor, endpoint in (
        (owner, reverse("schedule-operations")),
        (manager, reverse("schedule-operations")),
        (physiotherapist, reverse("schedule-assigned-me")),
    ):
        api_client.force_authenticate(actor)
        response = api_client.get(endpoint, **headers(organization))
        assert response.status_code == 200
        assert otp not in str(response.data)
        assert "otp_hash" not in str(response.data)

    for actor in (owner, manager):
        api_client.force_authenticate(actor)
        denied = api_client.get(
            reverse("schedule-customer-visit-verification", args=[appointment.id]),
            **headers(organization),
        )
        assert denied.status_code == 403

    api_client.force_authenticate(physiotherapist)
    physiotherapist_state = api_client.get(
        reverse("schedule-physiotherapist-visit-verification", args=[appointment.id]),
        **headers(organization),
    )
    assert physiotherapist_state.status_code == 200
    assert otp not in str(physiotherapist_state.data)
    assert "otp" not in physiotherapist_state.data

    foreign_values, foreign_appointment = ready_appointment(api_client, "visit-foreign")
    api_client.force_authenticate(customer)
    denied = api_client.get(
        reverse("schedule-customer-visit-verification", args=[foreign_appointment.id]),
        **headers(organization),
    )
    assert denied.status_code == 404
    api_client.force_authenticate(None)
    unauthenticated = api_client.get(
        reverse("schedule-customer-visit-verification", args=[appointment.id]),
        **headers(organization),
    )
    assert unauthenticated.status_code == 401
    assert foreign_values[0] != organization


def test_disabled_identity_cannot_issue_or_verify(api_client):
    values, appointment = ready_appointment(api_client, "visit-disabled")
    organization, _, _, _, physiotherapist, _, customer, *_ = values
    customer.is_enabled = False
    customer.save(update_fields=("is_enabled",))
    api_client.force_authenticate(customer)
    assert (
        api_client.post(
            reverse("schedule-customer-visit-verification", args=[appointment.id]),
            {},
            format="json",
            **headers(organization),
        ).status_code
        == 403
    )
    customer.is_enabled = True
    customer.save(update_fields=("is_enabled",))
    issued = issue(api_client, values, appointment)
    physiotherapist.is_enabled = False
    physiotherapist.save(update_fields=("is_enabled",))
    assert verify(api_client, values, appointment, issued.data["otp"]).status_code == 403


def test_reissue_and_assignment_change_invalidate_old_otp(api_client):
    values, appointment = ready_appointment(api_client, "visit-invalidation")
    first = issue(api_client, values, appointment)
    second = issue(api_client, values, appointment)
    first_verification, current = list(
        VisitVerification.objects.filter(appointment=appointment).order_by("created_at")
    )
    assert first_verification.state == VisitVerification.State.INVALIDATED
    assert verify(api_client, values, appointment, first.data["otp"]).status_code == 400
    assert verify(api_client, values, appointment, second.data["otp"]).status_code == 200
    assert current.state == VisitVerification.State.AWAITING


def test_cancellation_invalidation_is_append_only_and_secret_free(api_client):
    values, appointment = ready_appointment(api_client, "visit-cancel-invalidation")
    issued = issue(api_client, values, appointment)
    verification = VisitVerification.objects.get(appointment=appointment)
    from apps.appointments.visit_verification import invalidate_active_visit_verifications

    invalidate_active_visit_verifications(
        appointment, reason="APPOINTMENT_CANCELLED", actor=values[2]
    )
    verification.refresh_from_db()
    assert verification.state == VisitVerification.State.INVALIDATED
    events = list(verification.audit_events.values("event", "reason_code", "outcome"))
    assert any(event["event"] == "INVALIDATED" for event in events)
    assert issued.data["otp"] not in str(events)
    assert "pbkdf2" not in str(events)


def test_reschedule_and_cancellation_services_invalidate_active_otp(api_client):
    values, appointment = ready_appointment(api_client, "visit-reschedule")
    issue(api_client, values, appointment)
    reschedule_appointment(
        appointment,
        scheduled_start=start_at(days=1, hour=10),
        duration_minutes=60,
        actor=values[2],
        allow_override=True,
        override_reason="Customer-approved operational correction",
    )
    verification = VisitVerification.objects.get(appointment=appointment)
    assert verification.state == VisitVerification.State.INVALIDATED
    assert verification.invalidation_reason == "APPOINTMENT_RESCHEDULED"

    values, appointment = ready_appointment(api_client, "visit-cancel")
    issue(api_client, values, appointment)
    cancel_appointment(
        appointment,
        category=Appointment.CancellationCategory.CUSTOMER_REQUEST,
        reason="Customer requested cancellation",
        actor=values[2],
        allow_override=True,
        override_reason="Customer confirmed late cancellation",
    )
    verification = VisitVerification.objects.get(appointment=appointment)
    assert verification.state == VisitVerification.State.INVALIDATED
    assert verification.invalidation_reason == "APPOINTMENT_CANCELLED"


def test_reassignment_invalidates_otp_and_old_therapist_cannot_verify(api_client, monkeypatch):
    values, appointment = ready_appointment(api_client, "visit-reassign")
    organization, clinic, owner, _, old_user, _, _, *_ = values
    issued = issue(api_client, values, appointment)
    new_user = add_actor(organization, clinic, "PHYSIOTHERAPIST", "visit-reassign-new")
    new_profile = StaffProfile.objects.create(
        user=new_user,
        organization=organization,
        clinic=clinic,
        staff_type="PHYSIOTHERAPIST",
        gender="FEMALE",
        date_of_birth=date(1992, 1, 1),
        qualification="BPT",
        experience_years=4,
        languages_known=["Hindi"],
        emergency_contact="9876543298",
        current_address="Meerut",
        city="Meerut",
        pin_code="250004",
        joining_date=date.today(),
    )
    monkeypatch.setattr(
        "apps.appointments.scheduling.ensure_physiotherapist_available",
        lambda **kwargs: None,
    )
    assign_physiotherapist(
        appointment,
        physiotherapist=new_profile,
        actor=owner,
        reason="Coverage reassignment",
    )
    verification = VisitVerification.objects.get(appointment=appointment)
    assert verification.state == VisitVerification.State.INVALIDATED
    assert verification.invalidation_reason == "ASSIGNMENT_CHANGED"
    api_client.force_authenticate(old_user)
    denied = api_client.post(
        reverse("schedule-physiotherapist-visit-verification", args=[appointment.id]),
        {"otp": issued.data["otp"]},
        format="json",
        **headers(organization),
    )
    assert denied.status_code == 400
    assert verification.audit_events.filter(
        event=VisitVerificationAuditEvent.Event.UNAUTHORIZED,
        reason_code="ASSIGNMENT_MISMATCH",
    ).exists()
