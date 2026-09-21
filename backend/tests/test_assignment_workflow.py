from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from django.db import close_old_connections, connection, connections
from django.urls import reverse

from apps.accounts.models import Notification
from apps.appointments.models import Appointment, AppointmentChangeRequest, AppointmentPayment, AppointmentRequest
from apps.appointments.scheduling import assign_physiotherapist
from tests.test_appointment_operations import create_scheduled
from tests.test_scheduling import headers, setup_domain, start_at

pytestmark = pytest.mark.django_db


def test_prepaid_booking_requires_owner_verification_before_assignment(
    api_client, django_capture_on_commit_callbacks
):
    values = setup_domain("prepaid-verification")
    organization, _, owner, manager, _, physiotherapist, customer, *_rest, therapy = values
    physiotherapist.therapy_competencies.add(therapy)
    customer.mobile_number = "+919876543210"
    customer.save(update_fields=("mobile_number",))
    slot = start_at(days=2, hour=10)
    api_client.force_authenticate(customer)
    created = api_client.post(
        reverse("quick-appointment-create"),
        {
            "therapy": str(therapy.id),
            "requested_therapies": [],
            "preferred_date": slot.date().isoformat(),
            "preferred_time": slot.time().strftime("%H:%M"),
            "pain_area": "",
        },
        format="json",
        **headers(organization),
    )
    assert created.status_code == 201, created.data
    source = AppointmentRequest.objects.get(pk=created.data["id"])
    appointment = source.operational_appointment
    assert appointment.status == Appointment.Status.PENDING_ASSIGNMENT
    assert appointment.assignment_status == Appointment.AssignmentStatus.UNASSIGNED
    assert appointment.payment.status == AppointmentPayment.Status.PENDING

    api_client.force_authenticate(owner)
    blocked_assignment = api_client.post(
        reverse("schedule-assign", args=[appointment.id]),
        {"physiotherapist": str(physiotherapist.id)},
        format="json",
        **headers(organization),
    )
    assert blocked_assignment.status_code == 400

    api_client.force_authenticate(customer)
    submitted = api_client.post(
        reverse("customer-payment-submission", args=[appointment.id]),
        {"acknowledged": True},
        format="json",
        **headers(organization),
    )
    duplicate = api_client.post(
        reverse("customer-payment-submission", args=[appointment.id]),
        {"acknowledged": True},
        format="json",
        **headers(organization),
    )
    appointment.payment.refresh_from_db()
    assert submitted.status_code == 200 and duplicate.status_code == 400
    assert appointment.payment.status == AppointmentPayment.Status.VERIFICATION_PENDING

    api_client.force_authenticate(manager)
    manager_denied = api_client.post(
        reverse("schedule-operations-payment", args=[appointment.id]),
        {"status": "PAID"},
        format="json",
        **headers(organization),
    )
    assert manager_denied.status_code == 403

    api_client.force_authenticate(owner)
    verified = api_client.post(
        reverse("schedule-operations-payment", args=[appointment.id]),
        {"status": "PAID", "reference": "OWNER-VERIFIED"},
        format="json",
        **headers(organization),
    )
    appointment.refresh_from_db()
    appointment.payment.refresh_from_db()
    source.refresh_from_db()
    assert verified.status_code == 200
    assert appointment.payment.status == AppointmentPayment.Status.PAID
    assert appointment.status == Appointment.Status.SCHEDULED
    assert source.status == AppointmentRequest.Status.APPROVED

    available = api_client.get(
        reverse("appointment-request-eligible", args=[source.id]),
        **headers(organization),
    )
    assert available.status_code == 200
    candidate = next(item for item in available.data if item["id"] == str(physiotherapist.id))
    assert candidate["eligible"] is True
    assert candidate["eligibility_reason"] == "Available for this requested time"

    assignment_version = appointment.updated_at.isoformat()
    with django_capture_on_commit_callbacks(execute=True):
        assigned = api_client.post(
            reverse("schedule-assign", args=[appointment.id]),
            {
                "physiotherapist": str(physiotherapist.id),
                "expected_updated_at": assignment_version,
            },
            format="json",
            **headers(organization),
        )
        stale_assignment = api_client.post(
            reverse("schedule-assign", args=[appointment.id]),
            {
                "physiotherapist": str(physiotherapist.id),
                "expected_updated_at": assignment_version,
            },
            format="json",
            **headers(organization),
        )
    assert assigned.status_code == 200
    assert stale_assignment.status_code == 400
    assert assigned.data["assignment_status"] == Appointment.AssignmentStatus.PENDING
    assert Notification.objects.filter(
        recipient=physiotherapist.user,
        notification_type="APPOINTMENT_ASSIGNED",
    ).count() == 1
    assert Notification.objects.filter(
        recipient=customer,
        notification_type="THERAPIST_ASSIGNED",
    ).count() == 1

    foreign_values = setup_domain("prepaid-verification-foreign")
    foreign_organization, _, foreign_owner, _, _, foreign_physiotherapist, *_ = foreign_values
    api_client.force_authenticate(foreign_owner)
    hidden_candidates = api_client.get(
        reverse("appointment-request-eligible", args=[source.id]),
        **headers(foreign_organization),
    )
    hidden_assignment = api_client.post(
        reverse("schedule-assign", args=[appointment.id]),
        {"physiotherapist": str(foreign_physiotherapist.id)},
        format="json",
        **headers(foreign_organization),
    )
    assert hidden_candidates.status_code == 404
    assert hidden_assignment.status_code == 404


def test_assignment_acceptance_and_rejection_are_owned_and_audited(api_client):
    values = setup_domain("dispatch-response")
    organization, _, owner, _, physio_user, _, customer, *_ = values
    appointment = create_scheduled(api_client, values)
    appointment.refresh_from_db()
    assert appointment.assignment_status == Appointment.AssignmentStatus.PENDING
    assert appointment.assigned_by == owner

    api_client.force_authenticate(customer)
    denied = api_client.post(
        reverse("schedule-assignment-response", args=[appointment.id]),
        {"accept": True},
        format="json",
        **headers(organization),
    )
    api_client.force_authenticate(physio_user)
    accepted = api_client.post(
        reverse("schedule-assignment-response", args=[appointment.id]),
        {"accept": True},
        format="json",
        **headers(organization),
    )
    appointment.refresh_from_db()
    assert denied.status_code == 403 and accepted.status_code == 200
    assert appointment.assignment_status == Appointment.AssignmentStatus.ACCEPTED
    assert appointment.audit_events.filter(event="ASSIGNMENT_ACCEPTED", actor=physio_user).exists()


def test_rejection_requires_reason_and_reassignment_resets_response(api_client):
    values = setup_domain("dispatch-reject")
    organization, _, owner, manager, physio_user, physiotherapist, *_ = values
    appointment = create_scheduled(api_client, values)
    api_client.force_authenticate(physio_user)
    missing = api_client.post(
        reverse("schedule-assignment-response", args=[appointment.id]),
        {"accept": False, "reason": ""},
        format="json",
        **headers(organization),
    )
    rejected = api_client.post(
        reverse("schedule-assignment-response", args=[appointment.id]),
        {"accept": False, "reason": "Unable to cover this visit"},
        format="json",
        **headers(organization),
    )
    api_client.force_authenticate(manager)
    reassigned = api_client.post(
        reverse("schedule-assign", args=[appointment.id]),
        {"physiotherapist": str(physiotherapist.id), "reason": "Dispatch retry"},
        format="json",
        **headers(organization),
    )
    appointment.refresh_from_db()
    assert missing.status_code == 400 and rejected.status_code == 200
    assert reassigned.status_code == 200
    assert appointment.assignment_status == Appointment.AssignmentStatus.PENDING
    assert appointment.assignment_rejection_reason == ""


def test_owner_or_manager_can_unassign_before_visit_and_audit_reason(api_client):
    values = setup_domain("dispatch-unassign")
    organization, _, _, manager, _, _, *_ = values
    appointment = create_scheduled(api_client, values)
    api_client.force_authenticate(manager)
    response = api_client.post(
        reverse("schedule-unassign", args=[appointment.id]),
        {"reason": "Coverage plan changed"},
        format="json",
        **headers(organization),
    )
    appointment.refresh_from_db()
    assert response.status_code == 200
    assert appointment.physiotherapist is None
    assert appointment.assignment_status == Appointment.AssignmentStatus.UNASSIGNED
    assert appointment.audit_events.filter(
        event="UNASSIGNED", reason="Coverage plan changed", actor=manager
    ).exists()


def test_customer_change_requests_do_not_mutate_schedule(api_client):
    values = setup_domain("dispatch-customer-change")
    organization, _, _, _, _, _, customer, *_ = values
    appointment = create_scheduled(api_client, values)
    original_start = appointment.scheduled_start
    api_client.force_authenticate(customer)
    response = api_client.post(
        reverse("schedule-customer-change-requests", args=[appointment.id]),
        {"kind": "CANCELLATION", "reason": "Please cancel this visit"},
        format="json",
        **headers(organization),
    )
    duplicate = api_client.post(
        reverse("schedule-customer-change-requests", args=[appointment.id]),
        {"kind": "CANCELLATION", "reason": "Duplicate request"},
        format="json",
        **headers(organization),
    )
    appointment.refresh_from_db()
    assert response.status_code == 201 and duplicate.status_code == 400
    assert appointment.scheduled_start == original_start
    assert appointment.status == Appointment.Status.SCHEDULED
    assert (
        AppointmentChangeRequest.objects.filter(
            appointment=appointment,
            kind=AppointmentChangeRequest.Kind.CANCELLATION,
            status=AppointmentChangeRequest.Status.PENDING,
        ).count()
        == 1
    )


def test_dispatch_search_workload_and_cross_tenant_scope(api_client):
    values = setup_domain("dispatch-search")
    organization, _, _, manager, _, physiotherapist, *_ = values
    appointment = create_scheduled(api_client, values)
    foreign = setup_domain("dispatch-foreign")
    create_scheduled(api_client, foreign)
    api_client.force_authenticate(manager)
    search = api_client.get(
        reverse("schedule-operations"),
        {"search": appointment.patient.full_name},
        **headers(organization),
    )
    workload = api_client.get(reverse("schedule-physiotherapist-workload"), **headers(organization))
    assert search.status_code == 200 and search.data["count"] == 1
    assert workload.status_code == 200 and len(workload.data) == 1
    assert workload.data[0]["id"] == str(physiotherapist.id)
    assert workload.data[0]["active_assignments"] == 1


@pytest.mark.django_db(transaction=True)
def test_postgresql_concurrent_prepaid_assignment_allows_only_one_overlap():
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL concurrency verification runs separately.")
    values = setup_domain("prepaid-assignment-concurrent")
    organization, clinic, owner, _, _, physiotherapist, _, patient, address, therapy = values
    slot = start_at(days=3, hour=11)
    appointments = []
    for _ in range(2):
        appointment = Appointment.objects.create(
            organization=organization,
            clinic=clinic,
            patient=patient,
            therapy=therapy,
            scheduled_start=slot,
            scheduled_end=slot + timedelta(minutes=45),
            duration_minutes=45,
            status=Appointment.Status.SCHEDULED,
            assignment_status=Appointment.AssignmentStatus.UNASSIGNED,
            address_line_1=address.address_line_1,
            city=address.city,
            region=address.region,
            pin_code=address.pin_code,
            created_by=owner,
            updated_by=owner,
        )
        AppointmentPayment.objects.create(
            appointment=appointment,
            organization=organization,
            amount_due="1900.00",
            status=AppointmentPayment.Status.PAID,
            updated_by=owner,
        )
        appointments.append(appointment.id)

    def assign_one(appointment_id):
        close_old_connections()
        try:
            assign_physiotherapist(
                Appointment.objects.get(pk=appointment_id),
                physiotherapist=type(physiotherapist).objects.get(pk=physiotherapist.id),
                actor=type(owner).objects.get(pk=owner.id),
                reason="Concurrent assignment test",
            )
            return "assigned"
        except Exception:
            return "rejected"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(assign_one, appointments))
    assert sorted(results) == ["assigned", "rejected"]
    assert Appointment.objects.filter(
        id__in=appointments,
        physiotherapist=physiotherapist,
        assignment_status=Appointment.AssignmentStatus.PENDING,
    ).count() == 1
