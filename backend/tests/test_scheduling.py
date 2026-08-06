from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.db import close_old_connections, connection, connections
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role, RoleAssignment, User
from apps.appointments.models import (
    Appointment,
    AppointmentAuditEvent,
    AppointmentRequest,
    ClinicOperatingHours,
    TherapyOption,
)
from apps.appointments.scheduling import save_scheduled_appointment
from apps.patients.models import PatientAddress, PatientProfile
from apps.staff.models import StaffProfile
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


def start_at(days=1, hour=10):
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
    organization, clinic, owner, _, _, physio, customer, patient, address, therapy = values
    api_client.force_authenticate(owner)
    api_client.post(
        reverse("schedule-list"),
        appointment_payload(clinic, patient, therapy, address, physio, "SCHEDULED"),
        format="json",
        **headers(organization),
    )
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
