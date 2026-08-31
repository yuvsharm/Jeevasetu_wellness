from datetime import UTC, date, datetime, timedelta
from unittest.mock import patch

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.appointments.models import Appointment, ClinicOperatingHours
from apps.availability.models import (
    AvailabilityAuditEvent,
    AvailabilityException,
    AvailabilityRule,
)
from apps.practitioners.models import PractitionerApplication, PractitionerCompetency, PractitionerProfile
from tests.test_scheduling import (
    appointment_payload,
    headers,
    setup_domain,
    start_at,
)

pytestmark = pytest.mark.django_db


def hours_payload(open_weekdays=range(7)):
    return {"minimum_advance_notice_hours": 24, "days": [
        {"weekday": weekday, "is_open": weekday in open_weekdays,
         "opens_at": "09:00" if weekday in open_weekdays else None,
         "closes_at": "18:00" if weekday in open_weekdays else None}
        for weekday in range(7)
    ]}


def test_owner_and_manager_configure_daily_hours_with_tenant_scope(api_client):
    organization, clinic, owner, manager, physio_user, *_ = setup_domain("hours-config")
    url = reverse("availability-operating-hours", args=[clinic.id])
    for actor in (owner, manager):
        api_client.force_authenticate(actor)
        payload = hours_payload({0, 1, 2, 3, 4, 5})
        payload["minimum_advance_notice_hours"] = 48
        response = api_client.put(url, payload, format="json", **headers(organization))
        assert response.status_code == 200 and response.data["days"][6]["is_open"] is False
        assert response.data["minimum_advance_notice_hours"] == 48
    api_client.force_authenticate(physio_user)
    assert api_client.put(url, hours_payload(), format="json", **headers(organization)).status_code == 403
    foreign = setup_domain("hours-foreign")
    api_client.force_authenticate(foreign[2])
    assert api_client.get(url, **headers(foreign[0])).status_code == 404


def test_customer_slots_fail_closed_for_missing_hours_and_closed_day(api_client):
    organization, clinic, _, _, _, _, customer, *_, therapy = setup_domain("customer-slot-policy")
    target = start_at(days=3)
    api_client.force_authenticate(customer)
    ClinicOperatingHours.objects.filter(clinic=clinic).delete()
    missing = api_client.get(reverse("availability-customer-slots"), {"therapy": therapy.id, "date": target.date()}, **headers(organization))
    assert missing.status_code == 409 and missing.data["code"] == "OPERATING_HOURS_UNAVAILABLE"
    ClinicOperatingHours.objects.create(
        clinic=clinic, weekdays=[target.weekday()], opens_at="09:00", closes_at="18:00",
        daily_schedule={str(target.weekday()): {"is_open": False, "opens_at": None, "closes_at": None}},
    )
    closed = api_client.get(reverse("availability-customer-slots"), {"therapy": therapy.id, "date": target.date()}, **headers(organization))
    assert closed.status_code == 200 and closed.data == []


def test_customer_slots_are_clinic_bookable_despite_one_practitioner_overlap(api_client):
    organization, clinic, owner, _, _, physio, customer, patient, address, therapy = setup_domain("customer-slot-overlap")
    target = start_at(days=3, hour=10)
    api_client.force_authenticate(owner)
    created = api_client.post(reverse("schedule-list"), appointment_payload(clinic, patient, therapy, address, physio, "SCHEDULED", start=target), format="json", **headers(organization))
    assert created.status_code == 201
    api_client.force_authenticate(customer)
    response = api_client.get(reverse("availability-customer-slots"), {"therapy": therapy.id, "date": target.date()}, **headers(organization))
    values = {item["value"] for item in response.data}
    assert response.status_code == 200 and target.strftime("%H:%M") in values


def test_customer_slots_ignore_practitioner_absence_and_availability(api_client):
    organization, clinic, owner, _, physio_user, physio, customer, *_, therapy = setup_domain("customer-slot-independent")
    target = start_at(days=3, hour=10)
    AvailabilityRule.objects.filter(physiotherapist=physio).update(is_active=False)
    AvailabilityException.objects.create(
        organization=organization,
        clinic=clinic,
        physiotherapist=physio,
        kind="UNAVAILABLE",
        starts_at=target,
        ends_at=target + timedelta(hours=4),
        reason="Approved leave",
        submitted_by=physio_user,
        approval_status="APPROVED",
        is_active=True,
        reviewed_by=owner,
    )
    api_client.force_authenticate(customer)
    response = api_client.get(
        reverse("availability-customer-slots"),
        {"therapy": therapy.id, "date": target.date()},
        **headers(organization),
    )
    assert response.status_code == 200
    assert target.strftime("%H:%M") in {item["value"] for item in response.data}


def test_customer_slots_hide_times_inside_advance_notice(api_client):
    organization, _, _, _, _, physio, customer, *_, therapy = setup_domain("customer-slot-notice")
    AvailabilityRule.objects.filter(physiotherapist=physio).update(effective_from=date(2026, 8, 27))
    now = datetime(2026, 8, 27, 4, 30, tzinfo=UTC)  # 10:00 clinic-local
    api_client.force_authenticate(customer)
    with patch("apps.appointments.scheduling.timezone.now", return_value=now):
        response = api_client.get(
            reverse("availability-customer-slots"),
            {"therapy": therapy.id, "date": "2026-08-28"},
            **headers(organization),
        )
    values = {item["value"] for item in response.data}
    assert response.status_code == 200
    assert "09:45" not in values and "10:00" in values


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


def test_owner_rule_creation_without_clinic_hours_fails_cleanly_and_rolls_back(api_client):
    organization, clinic, owner, _, _, physio, *_ = setup_domain("availability-no-hours")
    ClinicOperatingHours.objects.filter(clinic=clinic).delete()
    AvailabilityRule.objects.filter(physiotherapist=physio).delete()
    api_client.force_authenticate(owner)
    response = api_client.post(
        reverse("availability-rule-list"),
        {"clinic": clinic.id, "physiotherapist": physio.id, "weekday": 0, "starts_at": "10:00", "ends_at": "19:00", "effective_from": timezone.localdate()},
        format="json",
        **headers(organization),
    )
    assert response.status_code == 400
    assert "operating hours" in str(response.data).lower()
    assert not AvailabilityRule.objects.filter(physiotherapist=physio).exists()


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


def test_application_backed_slots_require_verified_therapy_competency(api_client):
    organization, clinic, owner, _, physio_user, physio, *_, therapy = setup_domain("availability-competency")
    application = PractitionerApplication.objects.create(
        applicant=physio_user,
        organization=organization,
        clinic=clinic,
        status=PractitionerApplication.Status.APPROVED,
        full_legal_name="Approved Practitioner",
    )
    profile = PractitionerProfile.objects.create(
        user=physio_user,
        organization=organization,
        clinic=clinic,
        staff_profile=physio,
        category=PractitionerApplication.Category.PHYSIOTHERAPIST,
        is_approved=True,
        is_open_to_work=True,
        approved_at=timezone.now(),
    )
    application.approved_profile = profile
    application.save(update_fields=("approved_profile",))
    target = start_at(days=3)
    params = {"clinic": clinic.id, "therapy": therapy.id, "date_from": target.date(), "date_to": target.date(), "physiotherapist": physio.id}
    api_client.force_authenticate(owner)
    assert api_client.get(reverse("availability-slots"), params, **headers(organization)).data == []
    PractitionerCompetency.objects.create(
        application=application,
        therapy=therapy,
        verification_status=PractitionerCompetency.Verification.VERIFIED,
    )
    assert api_client.get(reverse("availability-slots"), params, **headers(organization)).data


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
