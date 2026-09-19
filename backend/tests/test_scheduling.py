from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, time, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection, connections
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role, RoleAssignment, User
from apps.appointments.models import (
    Appointment,
    AppointmentAuditEvent,
    AppointmentPayment,
    AppointmentRequest,
    AppointmentRequestAuditEvent,
    AppointmentReminder,
    ClinicOperatingHours,
    TherapyOption,
)
from apps.appointments.scheduling import save_scheduled_appointment
from apps.appointments.scheduling import validate_schedule
from apps.availability.models import ApprovalStatus, AvailabilityRule
from apps.patients.models import PatientAddress, PatientProfile
from apps.practitioners.models import PractitionerApplication, PractitionerCompetency, PractitionerProfile
from apps.staff.models import ServiceArea, StaffProfile
from apps.tenancy.models import Clinic, ClinicMembership, Organization, OrganizationMembership

pytestmark = pytest.mark.django_db


def add_actor(organization, clinic, role, suffix):
    user = User.objects.create_user(
        username=f"{role.lower()}-{suffix}",
        email=f"{role.lower()}-{suffix}@example.com",
        password="Safe-test-password-1",
        first_name=role.title(),
        last_name="User",
    )
    membership = OrganizationMembership.objects.create(user=user, organization=organization)
    clinic_membership = None
    scoped_clinic = clinic if role in (Role.MANAGER, Role.PHYSIOTHERAPIST) else None
    if scoped_clinic:
        clinic_membership = ClinicMembership.objects.create(
            organization_membership=membership, clinic=clinic
        )
    RoleAssignment.objects.create(
        user=user,
        organization=organization,
        organization_membership=membership,
        clinic=scoped_clinic,
        clinic_membership=clinic_membership,
        role=role,
    )
    return user


def setup_domain(slug="schedule"):
    organization = Organization.objects.create(
        legal_name=slug,
        display_name=slug,
        slug=slug,
        timezone="Asia/Kolkata",
    )
    clinic = Clinic.objects.create(
        organization=organization,
        name="Meerut",
        slug="meerut",
        timezone="Asia/Kolkata",
    )
    ClinicOperatingHours.objects.create(
        clinic=clinic,
        weekdays=[0, 1, 2, 3, 4, 5, 6],
        opens_at=time(8),
        closes_at=time(20),
    )
    owner = add_actor(organization, clinic, Role.OWNER, slug)
    manager = add_actor(organization, clinic, Role.MANAGER, slug)
    physio_user = add_actor(organization, clinic, Role.PHYSIOTHERAPIST, slug)
    customer = add_actor(organization, clinic, Role.CUSTOMER, slug)
    physiotherapist = StaffProfile.objects.create(
        user=physio_user,
        organization=organization,
        clinic=clinic,
        staff_type=Role.PHYSIOTHERAPIST,
        gender="FEMALE",
        date_of_birth=date(1990, 1, 1),
        qualification="BPT",
        experience_years=5,
        languages_known=["Hindi"],
        emergency_contact="9876543299",
        current_address="Meerut",
        city="Meerut",
        pin_code="250004",
        joining_date=date.today(),
    )
    for weekday in range(7):
        AvailabilityRule.objects.create(
            organization=organization,
            clinic=clinic,
            physiotherapist=physiotherapist,
            weekday=weekday,
            starts_at=time(8),
            ends_at=time(20),
            effective_from=timezone.localdate(),
            approval_status=ApprovalStatus.APPROVED,
            is_active=True,
            submitted_by=owner,
            reviewed_by=owner,
        )
    patient = PatientProfile.objects.create(
        organization=organization,
        clinic=clinic,
        user=customer,
        full_name="Asha Sharma",
        mobile_number="9876543210",
        gender="FEMALE",
        age=28,
        emergency_contact_name="Yash Sharma",
        emergency_contact_relationship="Brother",
        emergency_contact_mobile="9876543299",
    )
    address = PatientAddress.objects.create(
        patient=patient,
        address_line_1="Shastri Nagar",
        city="Meerut",
        region="Uttar Pradesh",
        pin_code="250004",
        is_primary=True,
    )
    therapy = TherapyOption.objects.create(
        organization=organization,
        name="Physiotherapy",
        slug="physiotherapy",
        default_duration_minutes=45,
    )
    return (
        organization,
        clinic,
        owner,
        manager,
        physio_user,
        physiotherapist,
        customer,
        patient,
        address,
        therapy,
    )


def start_at(days=2, hour=10):
    local = timezone.now().astimezone(ZoneInfo("Asia/Kolkata")) + timedelta(days=days)
    return datetime.combine(local.date(), time(hour), ZoneInfo("Asia/Kolkata"))


def headers(organization):
    return {"HTTP_X_ORGANIZATION_SLUG": organization.slug}


def appointment_payload(
    clinic, patient, therapy, address, physiotherapist=None, status="DRAFT", start=None
):
    return {
        "clinic": str(clinic.id),
        "patient": str(patient.id),
        "therapy": str(therapy.id),
        "physiotherapist": str(physiotherapist.id) if physiotherapist else None,
        "scheduled_start": (start or start_at()).isoformat(),
        "status": status,
        "address_line_1": address.address_line_1,
        "address_line_2": "",
        "landmark": "Near park",
        "city": address.city,
        "region": address.region,
        "pin_code": address.pin_code,
        "operational_notes": "Bring portable table.",
    }


def test_owner_creates_with_therapy_duration_and_address_snapshot(api_client):
    values = setup_domain("schedule-create")
    organization, clinic, owner, _, _, physio, _, patient, address, therapy = values
    api_client.force_authenticate(owner)
    response = api_client.post(
        reverse("schedule-list"),
        appointment_payload(clinic, patient, therapy, address, physio, "SCHEDULED"),
        format="json",
        **headers(organization),
    )
    appointment = Appointment.objects.get(pk=response.data["id"])
    address.address_line_1 = "Changed later"
    address.save()
    assert response.status_code == 201
    assert appointment.duration_minutes == 45
    assert appointment.address_line_1 == "Shastri Nagar"
    assert AppointmentAuditEvent.objects.filter(appointment=appointment).count() == 1


def test_notice_horizon_and_operating_hours_are_enforced(api_client):
    values = setup_domain("schedule-hours")
    organization, clinic, owner, _, _, _, _, patient, address, therapy = values
    api_client.force_authenticate(owner)
    too_soon = timezone.now() + timedelta(minutes=30)
    too_late = timezone.now() + timedelta(days=91)
    outside = start_at(hour=21)
    results = [
        api_client.post(
            reverse("schedule-list"),
            appointment_payload(clinic, patient, therapy, address, start=value),
            format="json",
            **headers(organization),
        ).status_code
        for value in (too_soon, too_late, outside)
    ]
    assert results == [400, 400, 400]


def test_configurable_advance_notice_exact_boundary_and_timezone():
    _, clinic, *_ = setup_domain("schedule-notice-boundary")
    hours = clinic.appointment_operating_hours
    hours.minimum_advance_notice_hours = 24
    hours.save(update_fields=("minimum_advance_notice_hours",))
    now = datetime(2026, 8, 27, 4, 30, tzinfo=UTC)  # 10:00 Asia/Kolkata
    with patch("apps.appointments.scheduling.timezone.now", return_value=now):
        assert validate_schedule(clinic=clinic, start=now + timedelta(hours=24), duration_minutes=45)
        with pytest.raises(ValidationError, match="at least 24 hours"):
            validate_schedule(clinic=clinic, start=now + timedelta(hours=23, minutes=59), duration_minutes=45)
        assert validate_schedule(clinic=clinic, start=now + timedelta(hours=25), duration_minutes=45)


def test_configured_notice_other_than_twenty_four_hours_is_enforced():
    _, clinic, *_ = setup_domain("schedule-notice-custom")
    hours = clinic.appointment_operating_hours
    hours.minimum_advance_notice_hours = 48
    hours.save(update_fields=("minimum_advance_notice_hours",))
    now = datetime(2026, 8, 27, 4, 30, tzinfo=UTC)
    with patch("apps.appointments.scheduling.timezone.now", return_value=now):
        with pytest.raises(ValidationError, match="at least 48 hours"):
            validate_schedule(clinic=clinic, start=now + timedelta(hours=47, minutes=59), duration_minutes=45)
        assert validate_schedule(clinic=clinic, start=now + timedelta(hours=48), duration_minutes=45)


def test_blocking_overlap_is_rejected(api_client):
    values = setup_domain("schedule-overlap")
    organization, clinic, owner, _, _, physio, _, patient, address, therapy = values
    api_client.force_authenticate(owner)
    data = appointment_payload(clinic, patient, therapy, address, physio, "SCHEDULED")
    first = api_client.post(reverse("schedule-list"), data, format="json", **headers(organization))
    second = api_client.post(reverse("schedule-list"), data, format="json", **headers(organization))
    assert first.status_code == 201 and second.status_code == 400


def test_status_flow_and_final_state_reschedule_protection(api_client):
    values = setup_domain("schedule-flow")
    organization, clinic, owner, _, _, physio, _, patient, address, therapy = values
    api_client.force_authenticate(owner)
    created = api_client.post(
        reverse("schedule-list"),
        appointment_payload(clinic, patient, therapy, address, physio, "SCHEDULED"),
        format="json",
        **headers(organization),
    )
    appointment_id = created.data["id"]
    statuses = []
    for new_status in ("CONFIRMED", "IN_PROGRESS", "COMPLETED"):
        if new_status == "IN_PROGRESS":
            Appointment.objects.filter(pk=appointment_id).update(
                assignment_status=Appointment.AssignmentStatus.ACCEPTED,
                journey_status=Appointment.JourneyStatus.REACHED,
                en_route_at=timezone.now(),
            )
        result = api_client.post(
            reverse("schedule-status", args=[appointment_id]),
            {"status": new_status, "reason": "Approved workflow"},
            format="json",
            **headers(organization),
        )
        statuses.append(result.status_code)
    reschedule = api_client.patch(
        reverse("schedule-detail", args=[appointment_id]),
        {"scheduled_start": start_at(days=2).isoformat()},
        format="json",
        **headers(organization),
    )
    assert statuses == [200, 200, 200] and reschedule.status_code == 400


def test_unassigned_cannot_be_scheduled_or_confirmed(api_client):
    values = setup_domain("schedule-unassigned")
    organization, clinic, owner, _, _, _, _, patient, address, therapy = values
    api_client.force_authenticate(owner)
    invalid = api_client.post(
        reverse("schedule-list"),
        appointment_payload(clinic, patient, therapy, address, status="SCHEDULED"),
        format="json",
        **headers(organization),
    )
    draft = api_client.post(
        reverse("schedule-list"),
        appointment_payload(clinic, patient, therapy, address),
        format="json",
        **headers(organization),
    )
    confirmed = api_client.post(
        reverse("schedule-status", args=[draft.data["id"]]),
        {"status": "CONFIRMED"},
        format="json",
        **headers(organization),
    )
    assert invalid.status_code == 400 and draft.status_code == 201 and confirmed.status_code == 400


def test_conversion_requires_explicit_patient_and_is_idempotent(api_client):
    values = setup_domain("schedule-convert")
    organization, clinic, owner, _, _, physio, _, patient, address, therapy = values
    source = AppointmentRequest.objects.create(
        organization=organization,
        therapy=therapy,
        patient_name="Unlinked request",
        age=30,
        gender="FEMALE",
        mobile_number="9876543211",
        session_preference="SINGLE",
        preferred_date=start_at().date(),
        preferred_time=time(10),
        problem_description="Mobility concern",
        pain_area="Knee",
        problem_duration="Two weeks",
        address="Request address",
        city="Meerut",
        pin_code="250004",
        landmark="Park",
        status=AppointmentRequest.Status.APPROVED,
    )
    api_client.force_authenticate(owner)
    missing_patient = appointment_payload(clinic, patient, therapy, address, physio, "SCHEDULED")
    missing_patient.pop("patient")
    rejected = api_client.post(
        reverse("schedule-convert", args=[source.id]),
        missing_patient,
        format="json",
        **headers(organization),
    )
    data = appointment_payload(clinic, patient, therapy, address, physio, "SCHEDULED")
    first = api_client.post(
        reverse("schedule-convert", args=[source.id]), data, format="json", **headers(organization)
    )
    second = api_client.post(
        reverse("schedule-convert", args=[source.id]), data, format="json", **headers(organization)
    )
    assert rejected.status_code == 400
    assert first.status_code == 201 and second.status_code == 200
    assert Appointment.objects.filter(originating_request=source).count() == 1


def test_request_accept_and_assign_is_atomic_and_schedules_reminders(api_client):
    values = setup_domain("request-decision")
    organization, _, owner, _, physio_user, physio, customer, _, _, therapy = values
    physio.therapy_competencies.add(therapy)
    source = AppointmentRequest.objects.create(
        organization=organization, creator=customer, therapy=therapy,
        patient_name="Asha Sharma", age=28, gender="FEMALE",
        mobile_number="9876543210", session_preference="SINGLE",
        preferred_date=start_at().date(), preferred_time=time(10),
        address="Shastri Nagar", city="Meerut", pin_code="250004",
        commercial_snapshot={"duration_minutes": 45, "final_amount": "1234.00"},
        regular_amount="1234.00", discount_amount="0.00", final_amount="1234.00",
    )
    second = TherapyOption.objects.create(
        organization=organization, name="Basti", slug="basti", default_duration_minutes=45,
    )
    source.requested_therapies.add(second)
    physio.therapy_competencies.add(second)
    api_client.force_authenticate(owner)
    response = api_client.post(
        reverse("appointment-request-decision", args=[source.id]),
        {"action": "ACCEPT_ASSIGN", "physiotherapist": str(physio.id)},
        format="json", **headers(organization),
    )
    assert response.status_code == 200
    appointment = Appointment.objects.get(originating_request=source)
    assert appointment.assignment_status == Appointment.AssignmentStatus.PENDING
    assert AppointmentRequestAuditEvent.objects.filter(
        appointment_request=source,
        event=AppointmentRequestAuditEvent.Event.APPROVED_AND_ASSIGNED,
    ).exists()
    api_client.force_authenticate(physio_user)
    accepted = api_client.post(
        reverse("schedule-assignment-response", args=[appointment.id]),
        {"accept": True}, format="json", **headers(organization),
    )
    assert accepted.status_code == 200
    assert AppointmentReminder.objects.filter(
        appointment=appointment, status=AppointmentReminder.Status.PENDING
    ).count() >= 1
    en_route = api_client.post(
        reverse("schedule-journey", args=[appointment.id]),
        {"journey_status": "EN_ROUTE"}, format="json", **headers(organization),
    )
    too_early = api_client.post(
        reverse("schedule-status", args=[appointment.id]),
        {"status": "IN_PROGRESS"}, format="json", **headers(organization),
    )
    reached = api_client.post(
        reverse("schedule-journey", args=[appointment.id]),
        {"journey_status": "REACHED"}, format="json", **headers(organization),
    )
    started = api_client.post(
        reverse("schedule-status", args=[appointment.id]),
        {"status": "IN_PROGRESS"}, format="json", **headers(organization),
    )
    completed = api_client.post(
        reverse("schedule-complete-and-confirm-payment", args=[appointment.id]),
        {"therapy_delivered": True, "payment_received": True},
        format="json", **headers(organization),
    )
    appointment.refresh_from_db()
    payment = AppointmentPayment.objects.get(appointment=appointment)
    assert (en_route.status_code, too_early.status_code, reached.status_code, started.status_code, completed.status_code) == (200, 400, 200, 200, 200)
    assert appointment.en_route_at and appointment.arrived_at and appointment.service_started_at and appointment.completed_at
    source.refresh_from_db()
    assert payment.amount_due == source.final_amount
    assert payment.status == AppointmentPayment.Status.PAID
    assert payment.updated_by == physio_user and payment.paid_at
    assert appointment.audit_events.filter(
        event=AppointmentAuditEvent.Event.JOURNEY_STATUS_CHANGED,
        reason=Appointment.JourneyStatus.EN_ROUTE,
    ).exists()
    assert appointment.audit_events.filter(
        event=AppointmentAuditEvent.Event.STATUS_CHANGED,
        new_status=Appointment.Status.COMPLETED,
    ).exists()
    original_address = appointment.address_line_1
    therapy.base_price = "1777.00"
    therapy.save(update_fields=("base_price",))
    api_client.force_authenticate(customer)
    rebooked = api_client.post(
        reverse("appointment-rebook", args=[appointment.id]),
        {"preferred_date": start_at(days=3).date(), "preferred_time": "10:00"},
        format="json", **headers(organization),
    )
    assert rebooked.status_code == 201
    repeated = AppointmentRequest.objects.get(pk=rebooked.data["id"])
    assert str(repeated.final_amount) == "1777.00"
    assert repeated.preferred_practitioner_id is None
    assert repeated.address == appointment.patient.addresses.get(is_primary=True).address_line_1
    appointment.refresh_from_db()
    assert appointment.address_line_1 == original_address


def test_request_accept_then_exact_slot_assignment_is_idempotent_and_customer_synced(api_client):
    values = setup_domain("request-two-step")
    organization, _, owner, _, physio_user, physio, customer, _, _, therapy = values
    profile = PractitionerProfile.objects.create(
        user=physio_user, organization=organization, clinic=physio.clinic,
        staff_profile=physio, category=PractitionerApplication.Category.PHYSIOTHERAPIST,
        is_approved=True, is_open_to_work=True, approved_at=timezone.now(),
    )
    source = AppointmentRequest.objects.create(
        organization=organization, creator=customer, therapy=therapy,
        patient_name="Asha Sharma", age=28, gender="FEMALE",
        mobile_number="9876543210", session_preference="SINGLE",
        preferred_date=start_at().date(), preferred_time=time(10),
        address="Shastri Nagar", city="Meerut", pin_code="250004",
        commercial_snapshot={"duration_minutes": 45}, regular_amount="0.00",
        discount_amount="0.00", final_amount="0.00",
    )
    second = TherapyOption.objects.create(
        organization=organization, name="Basti", slug="basti", default_duration_minutes=45,
    )
    source.requested_therapies.add(second)
    api_client.force_authenticate(owner)
    accepted = api_client.post(
        reverse("appointment-request-decision", args=[source.id]),
        {"action": "ACCEPT"}, format="json", **headers(organization),
    )
    source.refresh_from_db()
    assert accepted.status_code == 200 and source.status == AppointmentRequest.Status.APPROVED
    assert not Appointment.objects.filter(originating_request=source).exists()
    assert source.audit_events.filter(event=AppointmentRequestAuditEvent.Event.ACCEPTED).exists()
    missing = api_client.get(
        reverse("appointment-request-eligible", args=[source.id]), **headers(organization)
    )
    missing_item = next(item for item in missing.data if item["id"] == str(physio.id))
    assert missing_item["eligible"] is False
    assert missing_item["eligibility_reason"] == "Therapist does not currently offer Basti, Physiotherapy."
    api_client.force_authenticate(physio_user)
    requested = api_client.post(
        "/api/v1/staff/me/competencies/", {"therapy_id": str(therapy.id)},
        format="json", **headers(organization),
    )
    assert requested.status_code == 201
    assert requested.data["status"] == "SELECTED"
    assert physio.therapy_competencies.filter(pk=therapy.pk).exists()
    api_client.force_authenticate(owner)
    still_missing = api_client.get(
        reverse("appointment-request-eligible", args=[source.id]), **headers(organization)
    )
    assert next(item for item in still_missing.data if item["id"] == str(physio.id))["eligibility_reason"] == "Therapist does not currently offer Basti."
    api_client.force_authenticate(physio_user)
    assert api_client.post(
        "/api/v1/staff/me/competencies/", {"therapy_id": str(second.id)},
        format="json", **headers(organization),
    ).status_code == 201
    api_client.force_authenticate(owner)
    eligible = api_client.get(
        reverse("appointment-request-eligible", args=[source.id]), **headers(organization)
    )
    assert eligible.status_code == 200
    assert next(item for item in eligible.data if item["id"] == str(physio.id))["eligible"] is True
    assigned = api_client.post(
        reverse("appointment-request-decision", args=[source.id]),
        {"action": "ASSIGN", "physiotherapist": str(physio.id)},
        format="json", **headers(organization),
    )
    repeated = api_client.post(
        reverse("appointment-request-decision", args=[source.id]),
        {"action": "ASSIGN", "physiotherapist": str(physio.id)},
        format="json", **headers(organization),
    )
    appointment = Appointment.objects.get(originating_request=source)
    assert assigned.status_code == repeated.status_code == 200
    assert Appointment.objects.filter(originating_request=source).count() == 1
    assert appointment.scheduled_start.date() == source.preferred_date
    assert appointment.scheduled_start.astimezone(ZoneInfo("Asia/Kolkata")).time().replace(tzinfo=None) == source.preferred_time
    owner_view = api_client.get(reverse("appointment-owner-detail", args=[source.id]), **headers(organization))
    assert owner_view.status_code == 200
    api_client.force_authenticate(customer)
    history = api_client.get(reverse("appointment-mine"), **headers(organization))
    item = next(value for value in history.data if value["id"] == str(source.id))
    assert item["appointment"]["id"] == str(appointment.id)
    assert item["appointment"]["physiotherapist_name"] == physio.user.get_full_name()
    assert item["appointment"]["physiotherapist_age"] is not None
    assert item["appointment"]["physiotherapist_qualification"] == "BPT"
    assert item["appointment"]["physiotherapist_experience_years"] == 5
    assert item["appointment"]["requested_therapy_names"] == [therapy.name, second.name]
    assert [step["key"] for step in item["timeline"]][:4] == [
        "SUBMITTED", "REVIEW", "ACCEPTED", "ASSIGNED"
    ]
    api_client.force_authenticate(physio_user)
    assignments = api_client.get(reverse("schedule-assigned-me"), **headers(organization))
    assigned_item = next(value for value in assignments.data if value["id"] == str(appointment.id))
    assert assigned_item["assignment_status"] == "PENDING"
    assert owner_view.data["preferred_date"] == source.preferred_date.isoformat()
    assert owner_view.data["preferred_time"] == source.preferred_time.strftime("%H:%M:%S")
    assert assigned_item["scheduled_start"] == item["appointment"]["scheduled_start"]
    declined = api_client.post(
        reverse("schedule-assignment-response", args=[appointment.id]),
        {"accept": False, "reason": "Unavailable for this visit"},
        format="json", **headers(organization),
    )
    assert declined.status_code == 200
    api_client.force_authenticate(customer)
    detail = api_client.get(reverse("appointment-mine-detail", args=[source.id]), **headers(organization))
    assert detail.data["appointment"]["assignment_status"] == "REJECTED"
    appointment_target = api_client.get(
        reverse("appointment-mine-detail", args=[appointment.id]), **headers(organization)
    )
    assert appointment_target.status_code == 200
    assert appointment_target.data["id"] == str(source.id)
    api_client.force_authenticate(owner)
    assert api_client.get(
        reverse("appointment-mine-detail", args=[appointment.id]), **headers(organization)
    ).status_code == 403
    api_client.force_authenticate(customer)
    assert detail.data["appointment"]["physiotherapist_name"] is None
    assert detail.data["timeline"][-1]["key"] == "REASSIGNMENT"
    assert Appointment.objects.filter(originating_request=source).count() == 1


def test_request_eligibility_matches_canonical_service_area_when_pin_list_is_empty(api_client):
    values = setup_domain("request-canonical-area")
    organization, _, owner, _, _, physio, customer, _, _, therapy = values
    physio.therapy_competencies.add(therapy)
    meerut = ServiceArea.objects.create(
        organization=organization, name="Meerut", pin_codes=[]
    )
    physio.service_areas.add(meerut)
    source = AppointmentRequest.objects.create(
        organization=organization,
        creator=customer,
        therapy=therapy,
        patient_name="Asha Sharma",
        age=28,
        gender="FEMALE",
        mobile_number="9876543210",
        session_preference="SINGLE",
        preferred_date=start_at().date(),
        preferred_time=time(10),
        address="Shastri Nagar",
        city="  MEERUT  ",
        pin_code="240001",
        status=AppointmentRequest.Status.APPROVED,
    )
    api_client.force_authenticate(owner)

    response = api_client.get(
        reverse("appointment-request-eligible", args=[source.id]), **headers(organization)
    )
    item = next(value for value in response.data if value["id"] == str(physio.id))

    assert response.status_code == 200
    assert item["eligible"] is True
    assert item["eligibility_reason"] == "Available for this requested time"

    source.city = "Ghaziabad"
    source.save(update_fields=("city",))
    response = api_client.get(
        reverse("appointment-request-eligible", args=[source.id]), **headers(organization)
    )
    item = next(value for value in response.data if value["id"] == str(physio.id))
    assert item["eligible"] is False
    assert item["eligibility_reason"] == "The selected Physiotherapist does not serve this area."


def test_owner_offline_booking_creates_and_reuses_one_canonical_patient(api_client):
    values = setup_domain("offline-booking")
    organization, clinic, owner, _, _, physio, _, _, _, therapy = values
    therapy.base_price = "2900.00"
    therapy.save(update_fields=("base_price",))
    physio.therapy_competencies.add(therapy)
    meerut = ServiceArea.objects.create(
        organization=organization, name="Meerut", pin_codes=["250004"]
    )
    physio.service_areas.add(meerut)
    api_client.force_authenticate(owner)

    payload = {
        "mobile_number": "9876501111",
        "patient_name": "Offline Customer",
        "age": 41,
        "gender": "FEMALE",
        "clinic": str(clinic.id),
        "therapies": [str(therapy.id)],
        "physiotherapist": str(physio.id),
        "preferred_date": start_at(days=4).date().isoformat(),
        "preferred_time": "10:00",
        "service_address": {
            "address_line_1": "21 Civil Lines",
            "address_line_2": "",
            "landmark": "Near park",
            "city": "Meerut",
            "region": "Uttar Pradesh",
            "pin_code": "250004",
            "location_source": "MANUAL",
        },
        "booking_source": "CALL",
        "operational_note": "Customer called the front desk.",
        "payment_status": "PENDING",
        "payment_reference": "",
    }
    created = api_client.post(
        reverse("owner-offline-appointment-create"),
        payload,
        format="json",
        **headers(organization),
    )

    assert created.status_code == 201, created.data
    assert created.data["patient_reused"] is False
    assert created.data["payment_amount_due"] == "2900.00"
    patient = PatientProfile.objects.get(
        organization=organization, mobile_number=payload["mobile_number"]
    )
    assert patient.user_id is None
    assert patient.addresses.get(is_primary=True).address_line_1 == "21 Civil Lines"
    appointment = Appointment.objects.get(pk=created.data["id"])
    assert appointment.patient == patient
    assert appointment.originating_request.patient_profile == patient
    assert appointment.originating_request.booking_source == AppointmentRequest.BookingSource.CALL
    assert appointment.payment.status == AppointmentPayment.Status.PENDING

    payload.update({
        "preferred_date": start_at(days=5).date().isoformat(),
        "patient_name": "Ignored duplicate name",
    })
    payload.pop("service_address")
    reused = api_client.post(
        reverse("owner-offline-appointment-create"),
        payload,
        format="json",
        **headers(organization),
    )

    assert reused.status_code == 201, reused.data
    assert reused.data["patient_reused"] is True
    assert reused.data["patient_id"] == str(patient.id)
    assert PatientProfile.objects.filter(
        organization=organization, mobile_number=payload["mobile_number"], is_active=True
    ).count() == 1
    assert Appointment.objects.filter(patient=patient).count() == 2


def test_owner_request_list_is_paginated_eight_at_a_time(api_client):
    values = setup_domain("owner-request-pages")
    organization, _, owner, _, _, _, customer, _, _, therapy = values
    for index in range(9):
        AppointmentRequest.objects.create(
            organization=organization,
            creator=customer,
            therapy=therapy,
            patient_name=f"Customer {index}",
            age=30,
            gender="FEMALE",
            mobile_number=f"98765012{index:02d}",
            session_preference="SINGLE",
            preferred_date=start_at(days=index + 2).date(),
            preferred_time=time(10),
            address="Civil Lines",
            city="Meerut",
            pin_code="250004",
        )
    api_client.force_authenticate(owner)

    first = api_client.get(
        reverse("appointment-owner-list"), {"page_size": 8}, **headers(organization)
    )
    second = api_client.get(
        reverse("appointment-owner-list"), {"page_size": 8, "page": 2}, **headers(organization)
    )

    assert first.status_code == second.status_code == 200
    assert first.data["count"] == 9
    assert len(first.data["results"]) == 8
    assert first.data["next"] is not None
    assert len(second.data["results"]) == 1


def test_request_rejection_requires_customer_safe_structured_reason(api_client):
    values = setup_domain("request-reject")
    organization, _, owner, _, _, _, customer, _, _, therapy = values
    source = AppointmentRequest.objects.create(
        organization=organization, creator=customer, therapy=therapy,
        patient_name="Asha Sharma", age=28, gender="FEMALE",
        mobile_number="9876543210", session_preference="SINGLE",
        preferred_date=start_at().date(), preferred_time=time(10),
        address="Shastri Nagar", city="Meerut", pin_code="250004",
    )
    api_client.force_authenticate(owner)
    missing = api_client.post(
        reverse("appointment-request-decision", args=[source.id]),
        {"action": "REJECT"}, format="json", **headers(organization),
    )
    rejected = api_client.post(
        reverse("appointment-request-decision", args=[source.id]),
        {"action": "REJECT", "rejection_category": "SCHEDULING_CONFLICT",
         "customer_reason": "The requested slot is no longer available.",
         "internal_note": "Do not expose this note."},
        format="json", **headers(organization),
    )
    assert missing.status_code == 400 and rejected.status_code == 200
    assert rejected.data["rejection_customer_reason"] == "The requested slot is no longer available."
    assert "rejection_internal_note" not in rejected.data


def test_manager_scope_assignment_and_reassignment_audit(api_client):
    values = setup_domain("schedule-manager")
    organization, clinic, owner, manager, _, physio, _, patient, address, therapy = values
    second_user = add_actor(organization, clinic, Role.PHYSIOTHERAPIST, "second")
    second = StaffProfile.objects.create(
        user=second_user,
        organization=organization,
        clinic=clinic,
        staff_type=Role.PHYSIOTHERAPIST,
        gender="MALE",
        date_of_birth=date(1991, 1, 1),
        qualification="MPT",
        experience_years=4,
        languages_known=["Hindi"],
        emergency_contact="9876543288",
        current_address="Meerut",
        city="Meerut",
        pin_code="250004",
        joining_date=date.today(),
    )
    for weekday in range(7):
        AvailabilityRule.objects.create(
            organization=organization,
            clinic=clinic,
            physiotherapist=second,
            weekday=weekday,
            starts_at=time(8),
            ends_at=time(20),
            effective_from=timezone.localdate(),
            approval_status=ApprovalStatus.APPROVED,
            is_active=True,
            submitted_by=owner,
            reviewed_by=owner,
        )
    api_client.force_authenticate(owner)
    created = api_client.post(
        reverse("schedule-list"),
        appointment_payload(clinic, patient, therapy, address, physio, "SCHEDULED"),
        format="json",
        **headers(organization),
    )
    api_client.force_authenticate(manager)
    reassigned = api_client.post(
        reverse("schedule-assign", args=[created.data["id"]]),
        {"physiotherapist": str(second.id), "reason": "Roster change"},
        format="json",
        **headers(organization),
    )
    assert reassigned.status_code == 200
    assert (
        AppointmentAuditEvent.objects.filter(
            appointment_id=created.data["id"], event="REASSIGNED"
        ).count()
        == 1
    )


def test_physiotherapist_only_sees_assigned_and_allowed_transitions(api_client):
    values = setup_domain("schedule-physio")
    organization, clinic, owner, _, physio_user, physio, _, patient, address, therapy = values
    api_client.force_authenticate(owner)
    created = api_client.post(
        reverse("schedule-list"),
        appointment_payload(clinic, patient, therapy, address, physio, "SCHEDULED"),
        format="json",
        **headers(organization),
    )
    api_client.post(
        reverse("schedule-status", args=[created.data["id"]]),
        {"status": "CONFIRMED"},
        format="json",
        **headers(organization),
    )
    api_client.force_authenticate(physio_user)
    listed = api_client.get(reverse("schedule-assigned-me"), **headers(organization))
    cancelled = api_client.post(
        reverse("schedule-status", args=[created.data["id"]]),
        {"status": "CANCELLED"},
        format="json",
        **headers(organization),
    )
    Appointment.objects.filter(pk=created.data["id"]).update(
        assignment_status=Appointment.AssignmentStatus.ACCEPTED,
        journey_status=Appointment.JourneyStatus.REACHED,
        en_route_at=timezone.now(),
    )
    started = api_client.post(
        reverse("schedule-status", args=[created.data["id"]]),
        {"status": "IN_PROGRESS"},
        format="json",
        **headers(organization),
    )
    directory = api_client.get(reverse("patient-list-create"), **headers(organization))
    assert listed.status_code == 200 and len(listed.data) == 1
    assert "operational_notes" not in listed.data[0]
    assert cancelled.status_code == 403 and started.status_code == 200
    assert directory.status_code == 403


def test_customer_sees_safe_explicitly_linked_fields_only(api_client):
    values = setup_domain("schedule-customer")
    organization, clinic, owner, _, physio_user, physio, customer, patient, address, therapy = values
    api_client.force_authenticate(owner)
    api_client.post(
        reverse("schedule-list"),
        appointment_payload(clinic, patient, therapy, address, physio, "SCHEDULED"),
        format="json",
        **headers(organization),
    )
    appointment = Appointment.objects.get(organization=organization)
    api_client.force_authenticate(physio_user)
    accepted = api_client.post(
        reverse("schedule-assignment-response", args=[appointment.id]),
        {"accept": True},
        format="json",
        **headers(organization),
    )
    assert accepted.status_code == 200
    api_client.force_authenticate(customer)
    response = api_client.get(reverse("schedule-customer-me"), **headers(organization))
    assert response.status_code == 200 and len(response.data) == 1
    item = response.data[0]
    assert "operational_notes" not in item and "patient" not in item
    assert "mobile" not in str(item).lower() and "email" not in str(item).lower()
    assert item["physiotherapist_name"]


@pytest.mark.django_db(transaction=True)
def test_postgresql_concurrent_overlap_is_serialized():
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL concurrency verification runs separately.")
    values = setup_domain("schedule-concurrent")
    organization, clinic, owner, _, _, physio, _, patient, address, therapy = values
    scheduled_start = start_at()

    def create_one():
        close_old_connections()
        appointment = Appointment(
            organization=organization,
            clinic=clinic,
            patient=patient,
            therapy=therapy,
            physiotherapist=physio,
            scheduled_start=scheduled_start,
            scheduled_end=scheduled_start,
            duration_minutes=60,
            status=Appointment.Status.SCHEDULED,
            address_line_1=address.address_line_1,
            city=address.city,
            region=address.region,
            pin_code=address.pin_code,
            created_by=owner,
            updated_by=owner,
        )
        try:
            save_scheduled_appointment(
                appointment,
                actor=owner,
                event=AppointmentAuditEvent.Event.CREATED,
            )
            return "created"
        except Exception:
            return "rejected"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: create_one(), range(2)))
    assert sorted(results) == ["created", "rejected"]
