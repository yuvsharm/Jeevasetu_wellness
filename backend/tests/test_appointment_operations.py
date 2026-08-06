from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.appointments.models import Appointment
from tests.test_scheduling import (
    appointment_payload,
    headers,
    setup_domain,
    start_at,
)

pytestmark = pytest.mark.django_db


def create_scheduled(api_client, values, *, start=None):
    organization, clinic, owner, _, _, physio, _, patient, address, therapy = values
    api_client.force_authenticate(owner)
    response = api_client.post(
        reverse("schedule-list"),
        appointment_payload(
            clinic,
            patient,
            therapy,
            address,
            physio,
            "SCHEDULED",
            start=start,
        ),
        format="json",
        **headers(organization),
    )
    assert response.status_code == 201
    return Appointment.objects.get(pk=response.data["id"])


def test_manager_reschedules_and_rechecks_overlap_transactionally(api_client):
    values = setup_domain("operations-reschedule")
    organization, clinic, owner, manager, _, physio, _, patient, address, therapy = values
    first = create_scheduled(api_client, values, start=start_at(days=2, hour=10))
    create_scheduled(api_client, values, start=start_at(days=2, hour=12))
    api_client.force_authenticate(manager)
    conflict = api_client.post(
        reverse("schedule-reschedule", args=[first.id]),
        {"scheduled_start": start_at(days=2, hour=12), "duration_minutes": 45},
        format="json",
        **headers(organization),
    )
    successful = api_client.post(
        reverse("schedule-reschedule", args=[first.id]),
        {"scheduled_start": start_at(days=2, hour=14), "duration_minutes": 45},
        format="json",
        **headers(organization),
    )
    first.refresh_from_db()
    assert conflict.status_code == 400 and successful.status_code == 200, successful.data
    assert first.reschedule_count == 1
    assert first.audit_events.filter(event="RESCHEDULE_REJECTED", outcome="REJECTED").exists()


def test_reschedule_limit_and_owner_override_are_audited(api_client):
    values = setup_domain("operations-limit")
    organization, _, owner, manager, *_ = values
    appointment = create_scheduled(api_client, values)
    appointment.reschedule_count = 3
    appointment.save(update_fields=("reschedule_count",))
    api_client.force_authenticate(manager)
    denied = api_client.post(
        reverse("schedule-reschedule", args=[appointment.id]),
        {"scheduled_start": start_at(days=3), "duration_minutes": 45},
        format="json",
        **headers(organization),
    )
    manager_override = api_client.post(
        reverse("schedule-reschedule", args=[appointment.id]),
        {
            "scheduled_start": start_at(days=3),
            "duration_minutes": 45,
            "override": True,
            "override_reason": "Urgent continuity requirement",
        },
        format="json",
        **headers(organization),
    )
    api_client.force_authenticate(owner)
    missing_reason = api_client.post(
        reverse("schedule-reschedule", args=[appointment.id]),
        {
            "scheduled_start": start_at(days=3),
            "duration_minutes": 45,
            "override": True,
        },
        format="json",
        **headers(organization),
    )
    overridden = api_client.post(
        reverse("schedule-reschedule", args=[appointment.id]),
        {
            "scheduled_start": start_at(days=3),
            "duration_minutes": 45,
            "override": True,
            "override_reason": "Approved continuity exception",
        },
        format="json",
        **headers(organization),
    )
    audit = appointment.audit_events.filter(event="RESCHEDULED").latest("created_at")
    assert denied.status_code == 400 and manager_override.status_code == 403
    assert missing_reason.status_code == 400
    assert appointment.audit_events.filter(
        event="RESCHEDULE_REJECTED", rejection_code="OVERRIDE_REASON_REQUIRED"
    ).exists()
    assert overridden.status_code == 200 and audit.override_used
    assert audit.override_reason == "Approved continuity exception"


def test_cancellation_requires_category_reason_and_records_actor(api_client):
    values = setup_domain("operations-cancel")
    organization, _, owner, *_ = values
    appointment = create_scheduled(api_client, values)
    missing = api_client.post(
        reverse("schedule-cancel", args=[appointment.id]),
        {"operational_reason": "Requested by customer"},
        format="json",
        **headers(organization),
    )
    cancelled = api_client.post(
        reverse("schedule-cancel", args=[appointment.id]),
        {
            "reason_category": "CUSTOMER_REQUEST",
            "operational_reason": "Requested by customer",
        },
        format="json",
        **headers(organization),
    )
    appointment.refresh_from_db()
    assert missing.status_code == 400 and cancelled.status_code == 200
    assert appointment.status == "CANCELLED"
    assert appointment.cancelled_by == owner and appointment.cancelled_at
    assert appointment.cancellation_category == "CUSTOMER_REQUEST"


def test_cutoff_override_is_owner_only_and_rejections_are_safe(api_client):
    values = setup_domain("operations-cutoff")
    organization, _, owner, manager, *_ = values
    appointment = create_scheduled(api_client, values)
    appointment.scheduled_start = timezone.now() + timedelta(hours=1)
    appointment.scheduled_end = appointment.scheduled_start + timedelta(minutes=45)
    appointment.save(update_fields=("scheduled_start", "scheduled_end"))
    api_client.force_authenticate(manager)
    denied = api_client.post(
        reverse("schedule-cancel", args=[appointment.id]),
        {
            "reason_category": "CLINIC_OPERATIONAL_ISSUE",
            "operational_reason": "Clinic closure",
        },
        format="json",
        **headers(organization),
    )
    api_client.force_authenticate(owner)
    overridden = api_client.post(
        reverse("schedule-cancel", args=[appointment.id]),
        {
            "reason_category": "CLINIC_OPERATIONAL_ISSUE",
            "operational_reason": "Clinic closure",
            "override": True,
            "override_reason": "Emergency premises closure",
        },
        format="json",
        **headers(organization),
    )
    rejected = appointment.audit_events.get(event="CANCELLATION_REJECTED")
    accepted = appointment.audit_events.get(event="CANCELLED")
    assert denied.status_code == 400 and overridden.status_code == 200
    assert rejected.rejection_code == "CANCELLATION_CUTOFF" and rejected.reason == ""
    assert accepted.override_used and accepted.override_reason == "Emergency premises closure"


@pytest.mark.parametrize("state", ["IN_PROGRESS", "COMPLETED", "CANCELLED", "NO_SHOW"])
def test_locked_states_cannot_be_rescheduled_or_cancelled(api_client, state):
    values = setup_domain(f"operations-locked-{state.lower().replace('_', '-')}")
    organization, _, owner, *_ = values
    appointment = create_scheduled(api_client, values)
    appointment.status = state
    appointment.save(update_fields=("status",))
    reschedule = api_client.post(
        reverse("schedule-reschedule", args=[appointment.id]),
        {"scheduled_start": start_at(days=3), "duration_minutes": 45},
        format="json",
        **headers(organization),
    )
    cancel = api_client.post(
        reverse("schedule-cancel", args=[appointment.id]),
        {
            "reason_category": "OTHER",
            "operational_reason": "Operational correction",
        },
        format="json",
        **headers(organization),
    )
    assert reschedule.status_code == 400 and cancel.status_code == 400


def test_calendar_queue_filters_and_audit_are_clinic_scoped(api_client):
    values = setup_domain("operations-filters")
    organization, clinic, owner, _, _, physio, _, _, _, therapy = values
    appointment = create_scheduled(api_client, values)
    calendar = api_client.get(
        reverse("schedule-calendar"),
        {
            "clinic": clinic.id,
            "date_from": appointment.scheduled_start.date(),
            "date_to": appointment.scheduled_start.date(),
            "status": "SCHEDULED",
            "therapy": therapy.id,
            "physiotherapist": physio.id,
        },
        **headers(organization),
    )
    queue = api_client.get(reverse("schedule-operations"), **headers(organization))
    audit = api_client.get(
        reverse("schedule-audit", args=[appointment.id]), **headers(organization)
    )
    assert calendar.status_code == 200 and calendar.data["count"] == 1
    assert queue.status_code == 200 and queue.data["count"] == 1
    assert audit.status_code == 200 and audit.data["count"] == 1
    assert "operational_notes" not in calendar.data["results"][0]


def test_customer_disclosure_and_physio_mutation_boundaries(api_client):
    values = setup_domain("operations-safe-roles")
    organization, _, owner, _, physio_user, _, customer, *_ = values
    appointment = create_scheduled(api_client, values)
    api_client.force_authenticate(physio_user)
    physio_cancel = api_client.post(
        reverse("schedule-cancel", args=[appointment.id]),
        {"reason_category": "OTHER", "operational_reason": "Not permitted"},
        format="json",
        **headers(organization),
    )
    api_client.force_authenticate(customer)
    customer_cancel = api_client.post(
        reverse("schedule-cancel", args=[appointment.id]),
        {"reason_category": "CUSTOMER_REQUEST", "operational_reason": "Not permitted"},
        format="json",
        **headers(organization),
    )
    api_client.force_authenticate(owner)
    api_client.post(
        reverse("schedule-cancel", args=[appointment.id]),
        {
            "reason_category": "CUSTOMER_REQUEST",
            "operational_reason": "Requested through operations",
        },
        format="json",
        **headers(organization),
    )
    api_client.force_authenticate(customer)
    listed = api_client.get(reverse("schedule-customer-me"), **headers(organization))
    item = listed.data[0]
    assert physio_cancel.status_code == 403 and customer_cancel.status_code == 403
    assert item["cancellation_category"] == "CUSTOMER_REQUEST"
    assert "cancellation_reason" not in item and "operational_notes" not in item
    assert "email" not in str(item).lower() and "mobile" not in str(item).lower()
