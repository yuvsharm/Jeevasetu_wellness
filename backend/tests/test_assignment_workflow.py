import pytest
from django.urls import reverse

from apps.appointments.models import Appointment, AppointmentChangeRequest
from tests.test_appointment_operations import create_scheduled
from tests.test_scheduling import headers, setup_domain

pytestmark = pytest.mark.django_db


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
