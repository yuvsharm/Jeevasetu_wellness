from datetime import timedelta

import pytest
from django.urls import reverse

from apps.appointments.models import Appointment
from apps.availability.models import (
    AvailabilityAuditEvent,
    AvailabilityException,
    AvailabilityRule,
)
from tests.test_scheduling import (
    appointment_payload,
    headers,
    setup_domain,
    start_at,
)

pytestmark = pytest.mark.django_db


def test_physiotherapist_submits_own_rule_pending_manager_approves(api_client):
    values = setup_domain("availability-approval")
    organization, _, _, manager, physio_user, physio, *_ = values
    AvailabilityRule.objects.filter(physiotherapist=physio).delete()
    api_client.force_authenticate(physio_user)
    submitted = api_client.post(
        reverse("availability-me-rules"),
        {
            "weekday": 1,
            "starts_at": "09:00",
            "ends_at": "13:00",
            "effective_from": start_at().date(),
        },
        format="json",
        **headers(organization),
    )
    api_client.force_authenticate(manager)
    approved = api_client.post(
        reverse("availability-rule-review", args=[submitted.data["id"]]),
        {"approve": True, "reason": "Roster approved"},
        format="json",
        **headers(organization),
    )
    assert submitted.status_code == 201 and submitted.data["approval_status"] == "PENDING"
    assert approved.status_code == 200 and approved.data["is_active"]
    assert AvailabilityAuditEvent.objects.filter(rule_id=submitted.data["id"]).count() == 2


def test_physiotherapist_sees_only_own_request_history(api_client):
    values = setup_domain("availability-self")
    organization, clinic, owner, _, physio_user, physio, *_ = values
    other_values = setup_domain("availability-other")
    other_physio = other_values[5]
    AvailabilityException.objects.create(
        organization=organization,
        clinic=clinic,
        physiotherapist=physio,
        kind="UNAVAILABLE",
        starts_at=start_at(days=3),
        ends_at=start_at(days=3) + timedelta(hours=2),
        reason="Personal leave",
        submitted_by=physio_user,
    )
    api_client.force_authenticate(physio_user)
    response = api_client.get(reverse("availability-me-exceptions"), **headers(organization))
    foreign = api_client.post(
        reverse("availability-me-rules"),
        {
            "physiotherapist": other_physio.id,
            "weekday": 2,
            "starts_at": "09:00",
            "ends_at": "12:00",
            "effective_from": start_at().date(),
        },
        format="json",
        **headers(organization),
    )
    assert response.status_code == 200 and response.data["count"] == 1
    assert foreign.status_code == 201
    assert AvailabilityRule.objects.get(pk=foreign.data["id"]).physiotherapist == physio


def test_leave_conflicting_with_active_appointment_cannot_be_approved(api_client):
    values = setup_domain("availability-leave-conflict")
    organization, clinic, owner, manager, physio_user, physio, _, patient, address, therapy = values
    api_client.force_authenticate(owner)
    created = api_client.post(
        reverse("schedule-list"),
        appointment_payload(clinic, patient, therapy, address, physio, "SCHEDULED"),
        format="json",
        **headers(organization),
    )
    appointment = Appointment.objects.get(pk=created.data["id"])
    leave = AvailabilityException.objects.create(
        organization=organization,
        clinic=clinic,
        physiotherapist=physio,
        kind="UNAVAILABLE",
        starts_at=appointment.scheduled_start - timedelta(hours=1),
        ends_at=appointment.scheduled_end + timedelta(hours=1),
        reason="Approved leave request",
        submitted_by=physio_user,
    )
    api_client.force_authenticate(manager)
    response = api_client.post(
        reverse("availability-exception-review", args=[leave.id]),
        {"approve": True, "reason": "Review"},
        format="json",
        **headers(organization),
    )
    leave.refresh_from_db()
    assert response.status_code == 400 and leave.approval_status == "PENDING"
    assert AvailabilityAuditEvent.objects.filter(
        exception=leave, action="APPROVAL_BLOCKED", rejection_code="ACTIVE_APPOINTMENT_CONFLICT"
    ).exists()


def test_additional_availability_must_be_inside_clinic_hours(api_client):
    values = setup_domain("availability-additional")
    organization, clinic, _, manager, physio_user, physio, *_ = values
    outside = start_at(days=3, hour=7)
    request = AvailabilityException.objects.create(
        organization=organization,
        clinic=clinic,
        physiotherapist=physio,
        kind="ADDITIONAL_AVAILABILITY",
        starts_at=outside,
        ends_at=outside + timedelta(hours=1),
        reason="Early shift request",
        submitted_by=physio_user,
    )
    api_client.force_authenticate(manager)
    response = api_client.post(
        reverse("availability-exception-review", args=[request.id]),
        {"approve": True},
        format="json",
        **headers(organization),
    )
    assert response.status_code == 400


def test_operations_slot_discovery_uses_fifteen_minute_intervals_and_blocks_bookings(api_client):
    values = setup_domain("availability-slots")
    organization, clinic, owner, _, _, physio, _, patient, address, therapy = values
    target = start_at(days=3, hour=10)
    api_client.force_authenticate(owner)
    api_client.post(
        reverse("schedule-list"),
        appointment_payload(clinic, patient, therapy, address, physio, "SCHEDULED", start=target),
        format="json",
        **headers(organization),
    )
    response = api_client.get(
        reverse("availability-slots"),
        {
            "clinic": clinic.id,
            "therapy": therapy.id,
            "date_from": target.date(),
            "date_to": target.date(),
            "physiotherapist": physio.id,
        },
        **headers(organization),
    )
    starts = [item["scheduled_start"] for item in response.data]
    assert response.status_code == 200 and starts
    assert all(value.minute % 15 == 0 for value in starts)
    assert target not in starts


def test_appointment_paths_require_approved_availability(api_client):
    values = setup_domain("availability-enforced")
    organization, clinic, owner, _, _, physio, _, patient, address, therapy = values
    AvailabilityRule.objects.filter(physiotherapist=physio).update(is_active=False)
    api_client.force_authenticate(owner)
    response = api_client.post(
        reverse("schedule-list"),
        appointment_payload(clinic, patient, therapy, address, physio, "SCHEDULED"),
        format="json",
        **headers(organization),
    )
    assert response.status_code == 400


def test_customer_and_unrelated_staff_cannot_access_internal_availability(api_client):
    values = setup_domain("availability-private")
    organization, _, _, _, physio_user, _, customer, *_ = values
    api_client.force_authenticate(customer)
    slots = api_client.get(reverse("availability-slots"), **headers(organization))
    rules = api_client.get(reverse("availability-rule-list"), **headers(organization))
    api_client.force_authenticate(physio_user)
    audit = api_client.get(reverse("availability-audit"), **headers(organization))
    assert slots.status_code == 403 and rules.status_code == 403 and audit.status_code == 403
