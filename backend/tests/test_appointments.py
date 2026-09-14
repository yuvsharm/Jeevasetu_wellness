from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, time, timedelta
from unittest.mock import patch

import pytest
from django.db import close_old_connections, connection, connections
from django.urls import reverse
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Role, RoleAssignment, User
from apps.appointments.models import AppointmentRequest, BookingPhoneVerification, ClinicOperatingHours, TherapyOption
from apps.tenancy.models import Clinic, Organization, OrganizationMembership
from apps.tenancy.models import ClinicMembership
from apps.patients.models import CustomerFamilyMember, PatientAddress, PatientProfile
from apps.staff.models import StaffProfile
from apps.availability.models import ApprovalStatus, AvailabilityRule

pytestmark = pytest.mark.django_db


def setup_identity(role):
    organization = Organization.objects.create(
        legal_name="JeevaSetu",
        display_name="JeevaSetu",
        slug=f"org-{role.lower()}",
        timezone="Asia/Kolkata",
        default_currency="INR",
    )
    user = User.objects.create_user(
        username=f"{role.lower()}user",
        email=f"{role.lower()}@example.com",
        mobile_number="+919876543210" if role == Role.CUSTOMER else None,
        password="Safe-test-password-1",
    )
    membership = OrganizationMembership.objects.create(user=user, organization=organization)
    RoleAssignment.objects.create(
        user=user, organization=organization, organization_membership=membership, role=role
    )
    therapy = TherapyOption.objects.create(
        organization=organization, name="Abhyang", slug="abhyang"
    )
    if role == Role.CUSTOMER:
        clinic = Clinic.objects.create(
            organization=organization, name="Main Clinic", slug="main-clinic", timezone="Asia/Kolkata"
        )
        ClinicOperatingHours.objects.create(
            clinic=clinic, weekdays=list(range(7)), opens_at=time(9), closes_at=time(18)
        )
        patient = PatientProfile.objects.create(
            organization=organization, user=user, clinic=clinic, full_name="Asha Sharma",
            mobile_number="9876543210", gender="FEMALE", age=42,
            emergency_contact_name="Asha Sharma", emergency_contact_relationship="Self",
            emergency_contact_mobile="9876543210",
        )
        PatientAddress.objects.create(
            patient=patient, address_line_1="163 C Block", city="Meerut",
            region="Uttar Pradesh", pin_code="250004", is_primary=True,
        )
        physio_user = User.objects.create_user(
            username=f"physio-{organization.slug}", email=f"physio-{organization.slug}@example.com",
            password="Safe-test-password-1",
        )
        physio_membership = OrganizationMembership.objects.create(user=physio_user, organization=organization)
        clinic_membership = ClinicMembership.objects.create(organization_membership=physio_membership, clinic=clinic)
        RoleAssignment.objects.create(
            user=physio_user, organization=organization, organization_membership=physio_membership,
            clinic=clinic, clinic_membership=clinic_membership, role=Role.PHYSIOTHERAPIST,
        )
        physio = StaffProfile.objects.create(
            user=physio_user, organization=organization, clinic=clinic,
            staff_type=Role.PHYSIOTHERAPIST, gender="FEMALE", date_of_birth=date(1990, 1, 1),
            qualification="BPT", experience_years=5, languages_known=["Hindi"],
            emergency_contact="9876543299", current_address="Meerut", city="Meerut",
            pin_code="250004", joining_date=date.today(),
        )
        for weekday in range(7):
            AvailabilityRule.objects.create(
                organization=organization, clinic=clinic, physiotherapist=physio, weekday=weekday,
                starts_at=time(9), ends_at=time(18), effective_from=timezone.localdate(),
                approval_status=ApprovalStatus.APPROVED, is_active=True,
                submitted_by=physio_user, reviewed_by=physio_user,
            )
    return organization, user, therapy


def authenticated_payload(therapy, **overrides):
    return {
        "therapy": str(therapy.id),
        "requested_therapies": [],
        "family_member": None,
        "selected_package": None,
        "selected_offer": None,
        "preferred_date": str(timezone.localdate() + timedelta(days=2)),
        "preferred_time": "10:00",
        "pain_area": "",
        **overrides,
    }


def payload(therapy):
    return {
        "therapy": str(therapy.id),
        "patient_name": "Asha Sharma",
        "age": 42,
        "gender": "FEMALE",
        "mobile_number": "9876543210",
        "alternate_mobile": "",
        "email": "asha@example.com",
        "session_preference": "SINGLE",
        "preferred_date": str(timezone.localdate() + timedelta(days=2)),
        "preferred_time": "10:00",
        "problem_description": "Persistent lower back discomfort.",
        "pain_area": "Lower back",
        "problem_duration": "Three weeks",
        "doctor_reference": "",
        "address": "163 C Block, Shastri Nagar",
        "city": "Meerut",
        "pin_code": "250004",
        "landmark": "Near community park",
        "google_map_link": "",
    }


def tenant(slug):
    return {"HTTP_X_ORGANIZATION_SLUG": slug}


def test_authenticated_booking_requires_customer_not_therapist_availability_or_second_otp(api_client):
    organization, customer, therapy = setup_identity(Role.CUSTOMER)
    secondary = TherapyOption.objects.create(
        organization=organization, name="Kati Basti", slug="kati-basti"
    )
    url = reverse("quick-appointment-create")
    headers = tenant(organization.slug)
    data = authenticated_payload(therapy, requested_therapies=[str(therapy.id), str(secondary.id)])
    AvailabilityRule.objects.filter(organization=organization).update(is_active=False)
    assert api_client.post(url, data, format="json", **headers).status_code == 401
    api_client.force_authenticate(customer)
    created = api_client.post(url, data, format="json", **headers)
    assert created.status_code == 201
    assert created.data["status"] == "PENDING"
    request_value = AppointmentRequest.objects.get(pk=created.data["id"])
    assert request_value.patient_name == "Asha Sharma"
    assert request_value.age == 42
    assert request_value.gender == "FEMALE"
    assert request_value.mobile_number == "9876543210"
    assert str(request_value.preferred_date) == data["preferred_date"]
    assert request_value.preferred_time.strftime("%H:%M") == data["preferred_time"]
    assert set(request_value.requested_therapies.values_list("id", flat=True)) == {secondary.id}
    assert BookingPhoneVerification.objects.count() == 0
    assert api_client.post(url, data, format="json", **headers).status_code == 400


def test_authenticated_booking_snapshots_one_time_location_without_replacing_primary_by_default(api_client):
    organization, customer, therapy = setup_identity(Role.CUSTOMER)
    primary = PatientAddress.objects.get(patient__user=customer, is_primary=True)
    api_client.force_authenticate(customer)
    address = {
        "address_line_1": "42 Test Lane", "address_line_2": "Floor 2", "landmark": "Clock tower",
        "city": "Meerut", "region": "Uttar Pradesh", "pin_code": "250001",
        "latitude": "28.613900", "longitude": "77.209000",
        "location_accuracy_meters": 171, "location_source": "DEVICE",
    }
    created = api_client.post(
        reverse("quick-appointment-create"),
        authenticated_payload(therapy, service_address=address),
        format="json", **tenant(organization.slug),
    )
    assert created.status_code == 201
    request_value = AppointmentRequest.objects.get(pk=created.data["id"])
    assert request_value.address == "42 Test Lane Floor 2"
    assert request_value.location_accuracy_meters == 171
    assert request_value.location_source == "DEVICE"
    primary.refresh_from_db()
    assert primary.address_line_1 == "163 C Block"


@pytest.mark.django_db(transaction=True)
def test_concurrent_customer_requests_allow_distinct_customers_and_deduplicate_retries():
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL concurrency verification runs separately.")
    organization, first_customer, therapy = setup_identity(Role.CUSTOMER)
    clinic = Clinic.objects.get(organization=organization)
    second_customer = User.objects.create_user(
        username="customer-concurrent-second",
        email="customer-concurrent-second@example.com",
        mobile_number="+919876543211",
        password="Safe-test-password-1",
    )
    membership = OrganizationMembership.objects.create(
        user=second_customer, organization=organization
    )
    RoleAssignment.objects.create(
        user=second_customer,
        organization=organization,
        organization_membership=membership,
        role=Role.CUSTOMER,
    )
    second_profile = PatientProfile.objects.create(
        organization=organization,
        user=second_customer,
        clinic=clinic,
        full_name="TEST Concurrent Customer",
        mobile_number="9876543211",
        gender="FEMALE",
        age=35,
        emergency_contact_name="TEST Contact",
        emergency_contact_relationship="Friend",
        emergency_contact_mobile="9876543212",
    )
    PatientAddress.objects.create(
        patient=second_profile,
        address_line_1="TEST Concurrent Address",
        city="Meerut",
        region="Uttar Pradesh",
        pin_code="250004",
        is_primary=True,
    )
    request_data = authenticated_payload(therapy)

    def submit(customer):
        close_old_connections()
        client = APIClient()
        client.force_authenticate(customer)
        try:
            response = client.post(
                reverse("quick-appointment-create"),
                request_data,
                format="json",
                **tenant(organization.slug),
            )
            return response.status_code
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        distinct_results = list(executor.map(submit, (first_customer, second_customer)))
    assert sorted(distinct_results) == [201, 201]
    assert AppointmentRequest.objects.filter(organization=organization).count() == 2

    AppointmentRequest.objects.filter(organization=organization).update(
        status=AppointmentRequest.Status.CANCELLED
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        retry_results = list(executor.map(submit, (first_customer, first_customer)))
    assert sorted(retry_results) == [201, 400]
    assert AppointmentRequest.objects.filter(
        organization=organization,
        creator=first_customer,
        status=AppointmentRequest.Status.PENDING,
    ).count() == 1


def test_authenticated_booking_rejects_invalid_time_without_otp(api_client):
    organization, customer, therapy = setup_identity(Role.CUSTOMER)
    api_client.force_authenticate(customer)
    response = api_client.post(
        reverse("quick-appointment-create"),
        authenticated_payload(therapy, preferred_time="19:00"),
        format="json", **tenant(organization.slug),
    )
    assert response.status_code == 400
    assert "preferred_time" in response.data
    assert BookingPhoneVerification.objects.count() == 0


def test_authenticated_booking_fails_closed_without_operating_hours(api_client):
    organization, customer, therapy = setup_identity(Role.CUSTOMER)
    ClinicOperatingHours.objects.filter(clinic__organization=organization).delete()
    api_client.force_authenticate(customer)
    response = api_client.post(
        reverse("appointment-create"), authenticated_payload(therapy),
        format="json", **tenant(organization.slug),
    )
    assert response.status_code == 400
    assert str(response.data["detail"][0]) == "Online booking is temporarily unavailable because service hours have not been configured. Please contact JeevaSetu."


def test_direct_customer_request_inside_advance_notice_is_rejected(api_client):
    organization, customer, therapy = setup_identity(Role.CUSTOMER)
    api_client.force_authenticate(customer)
    now = datetime(2026, 8, 27, 4, 30, tzinfo=UTC)
    with patch("apps.appointments.scheduling.timezone.now", return_value=now):
        response = api_client.post(
            reverse("appointment-create"),
            authenticated_payload(therapy, preferred_date="2026-08-28", preferred_time="09:45"),
            format="json", **tenant(organization.slug),
        )
    assert response.status_code == 400
    assert "at least 24 hours' advance booking" in str(response.data["preferred_time"][0])


@override_settings(MSG91_ENABLED=False)
def test_customer_otp_login_authenticates_existing_customer_and_cannot_be_reused(api_client):
    organization, customer, _ = setup_identity(Role.CUSTOMER)
    api_client.force_authenticate(user=None)
    issued = api_client.post(reverse("booking-otp-issue"), {"mobile_number": "9876543210"}, format="json", **tenant(organization.slug))
    body = {"verification_id": issued.data["verification_id"], "mobile_number": "9876543210", "otp": issued.data["otp"]}
    logged_in = api_client.post(reverse("auth-customer-otp-login"), body, format="json", **tenant(organization.slug))
    assert logged_in.status_code == 200
    assert RoleAssignment.objects.filter(user=customer, organization=organization, role=Role.CUSTOMER, is_active=True).exists()
    assert BookingPhoneVerification.objects.get(pk=issued.data["verification_id"]).consumed_at is not None
    assert api_client.post(reverse("auth-customer-otp-login"), body, format="json", **tenant(organization.slug)).status_code == 400


def test_multi_therapy_duration_and_closing_time_are_enforced(api_client):
    organization, customer, therapy = setup_identity(Role.CUSTOMER)
    api_client.force_authenticate(customer)
    second = TherapyOption.objects.create(organization=organization, name="Nasya", slug="nasya")
    data = authenticated_payload(therapy, requested_therapies=[str(second.id)], preferred_time="16:30")
    created = api_client.post(reverse("quick-appointment-create"), data, format="json", **tenant(organization.slug))
    assert created.status_code == 201
    assert created.data["requested_duration_minutes"] == 90
    data |= {"preferred_time": "17:00"}
    assert api_client.post(reverse("quick-appointment-create"), data, format="json", **tenant(organization.slug)).status_code == 400


def test_customer_cannot_book_for_another_customers_family_member(api_client):
    organization, owner, therapy = setup_identity(Role.CUSTOMER)
    other = User.objects.create_user(username="other-customer", password="Safe-test-password-1")
    other_membership = OrganizationMembership.objects.create(user=other, organization=organization)
    RoleAssignment.objects.create(user=other, organization=organization, organization_membership=other_membership, role=Role.CUSTOMER)
    family = CustomerFamilyMember.objects.create(organization=organization, customer=other, full_name="Other Family", age=30, gender="OTHER", relationship="Sibling")
    api_client.force_authenticate(owner)
    data = authenticated_payload(therapy, family_member=str(family.id))
    response = api_client.post(reverse("appointment-create"), data, format="json", **tenant(organization.slug))
    assert response.status_code == 400
    assert "family_member" in response.data

def test_failed_authenticated_booking_does_not_create_verification(api_client):
    organization, customer, therapy = setup_identity(Role.CUSTOMER)
    api_client.force_authenticate(customer)
    data = authenticated_payload(therapy, preferred_time="19:00")
    response = api_client.post(
        reverse("quick-appointment-create"),
        data,
        format="json",
        **tenant(organization.slug),
    )
    assert response.status_code == 400
    assert BookingPhoneVerification.objects.count() == 0


def test_authenticated_create_validates_and_blocks_duplicate(api_client):
    organization, customer, therapy = setup_identity(Role.CUSTOMER)
    url = reverse("appointment-create")
    data = authenticated_payload(therapy)
    assert api_client.post(url, data, format="json", **tenant(organization.slug)).status_code == 401
    api_client.force_authenticate(customer)
    first = api_client.post(url, data, format="json", **tenant(organization.slug))
    duplicate = api_client.post(url, data, format="json", **tenant(organization.slug))
    assert first.status_code == 201
    assert first.data["status"] == "PENDING"
    assert duplicate.status_code == 400
    assert AppointmentRequest.objects.count() == 1


def test_active_therapy_list_is_tenant_scoped(api_client):
    organization, _, therapy = setup_identity(Role.CUSTOMER)
    TherapyOption.objects.create(
        organization=organization, name="Inactive", slug="inactive", is_active=False
    )
    response = api_client.get(reverse("appointment-therapy-list"), **tenant(organization.slug))
    assert response.status_code == 200
    assert response.data == [{"id": str(therapy.id), "name": "Abhyang", "slug": "abhyang"}]


def test_customer_only_sees_and_cancels_own_pending_request(api_client):
    organization, customer, therapy = setup_identity(Role.CUSTOMER)
    other = User.objects.create_user(
        username="other", email="other@example.com", password="Safe-test-password-1"
    )
    own = AppointmentRequest.objects.create(
        organization=organization,
        creator=customer,
        therapy=therapy,
        **{k: v for k, v in payload(therapy).items() if k != "therapy"},
    )
    hidden = AppointmentRequest.objects.create(
        organization=organization,
        creator=other,
        therapy=therapy,
        **{
            **{k: v for k, v in payload(therapy).items() if k != "therapy"},
            "mobile_number": "9876543211",
        },
    )
    api_client.force_authenticate(customer)
    response = api_client.get(reverse("appointment-mine"), **tenant(organization.slug))
    assert response.status_code == 200
    assert [item["id"] for item in response.data] == [str(own.id)]
    assert (
        api_client.get(
            reverse("appointment-mine-detail", args=[hidden.id]), **tenant(organization.slug)
        ).status_code
        == 404
    )
    cancelled = api_client.patch(
        reverse("appointment-cancel", args=[own.id]), {}, format="json", **tenant(organization.slug)
    )
    assert cancelled.status_code == 200
    own.refresh_from_db()
    assert own.status == AppointmentRequest.Status.CANCELLED


def test_owner_searches_and_updates_tenant_requests(api_client):
    organization, owner, therapy = setup_identity(Role.OWNER)
    request_value = AppointmentRequest.objects.create(
        organization=organization,
        creator=owner,
        therapy=therapy,
        **{k: v for k, v in payload(therapy).items() if k != "therapy"},
    )
    api_client.force_authenticate(owner)
    listed = api_client.get(
        reverse("appointment-owner-list"),
        {"search": "Asha", "status": "PENDING"},
        **tenant(organization.slug),
    )
    assert listed.status_code == 200
    assert listed.data["count"] == 1
    assert len(listed.data["results"]) == 1
    updated = api_client.patch(
        reverse("appointment-owner-detail", args=[request_value.id]),
        {"status": "APPROVED", "owner_remarks": "Confirmed by owner."},
        format="json",
        **tenant(organization.slug),
    )
    assert updated.status_code == 200
    request_value.refresh_from_db()
    assert request_value.status == AppointmentRequest.Status.APPROVED


def test_manager_searches_and_updates_tenant_requests(api_client):
    organization, manager, therapy = setup_identity(Role.MANAGER)
    request_value = AppointmentRequest.objects.create(
        organization=organization,
        creator=manager,
        therapy=therapy,
        **{k: v for k, v in payload(therapy).items() if k != "therapy"},
    )
    api_client.force_authenticate(manager)
    listed = api_client.get(
        reverse("appointment-owner-list"),
        {"search": "Asha", "status": "PENDING"},
        **tenant(organization.slug),
    )
    assert listed.status_code == 200
    assert listed.data["count"] == 1
    assert len(listed.data["results"]) == 1
    updated = api_client.patch(
        reverse("appointment-owner-detail", args=[request_value.id]),
        {"status": "APPROVED", "owner_remarks": "Confirmed by manager."},
        format="json",
        **tenant(organization.slug),
    )
    assert updated.status_code == 200
    request_value.refresh_from_db()
    assert request_value.status == AppointmentRequest.Status.APPROVED


def test_non_owner_cannot_access_owner_queue(api_client):
    organization, customer, _ = setup_identity(Role.CUSTOMER)
    api_client.force_authenticate(customer)
    assert (
        api_client.get(reverse("appointment-owner-list"), **tenant(organization.slug)).status_code
        == 403
    )


def test_server_rejects_past_date_and_cross_tenant_therapy(api_client):
    organization, customer, therapy = setup_identity(Role.CUSTOMER)
    other_org, _, other_therapy = setup_identity(Role.OWNER)
    api_client.force_authenticate(customer)
    invalid = authenticated_payload(
        other_therapy, preferred_date=str(timezone.localdate() - timedelta(days=1))
    )
    response = api_client.post(
        reverse("appointment-create"), invalid, format="json", **tenant(organization.slug)
    )
    assert response.status_code == 400
    assert "preferred_date" in response.data or "therapy" in response.data
    assert other_org != organization
    assert therapy.organization == organization


def test_authenticated_create_accepts_requested_therapies_and_validates_slot(api_client):
    organization, customer, therapy = setup_identity(Role.CUSTOMER)
    api_client.force_authenticate(customer)
    secondary = TherapyOption.objects.create(
        organization=organization, name="Kati Basti", slug="kati-basti"
    )
    tertiary = TherapyOption.objects.create(
        organization=organization, name="Nasya", slug="nasya"
    )

    valid = authenticated_payload(
        therapy, requested_therapies=[str(secondary.id), str(tertiary.id)]
    )
    response = api_client.post(
        reverse("appointment-create"), valid, format="json", **tenant(organization.slug)
    )
    assert response.status_code == 201
    request = AppointmentRequest.objects.get(pk=response.data["id"])
    assert set(str(item.id) for item in request.requested_therapies.all()) == {
        str(secondary.id),
        str(tertiary.id),
    }

    invalid = authenticated_payload(
        therapy, requested_therapies=[str(secondary.id)], preferred_time="19:00"
    )
    invalid_response = api_client.post(
        reverse("appointment-create"), invalid, format="json", **tenant(organization.slug)
    )
    assert invalid_response.status_code == 400
    assert "preferred_time" in invalid_response.data
