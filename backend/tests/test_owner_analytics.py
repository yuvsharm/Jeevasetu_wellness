from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.appointments.models import Appointment, AppointmentRating, AppointmentRequest, PractitionerPayment
from apps.patients.models import CustomerFamilyMember
from tests.test_appointment_operations import create_scheduled
from tests.test_scheduling import headers, setup_domain, start_at

pytestmark = pytest.mark.django_db


def make_request(values, *, amount="1000.00", discount="0.00", family_member=None, snapshot=None):
    organization, _, _, _, _, _, customer, _, _, therapy = values
    return AppointmentRequest.objects.create(
        organization=organization, creator=customer, family_member=family_member, therapy=therapy,
        patient_name="Asha Sharma", age=28, gender="FEMALE", mobile_number="9876543210",
        session_preference="SINGLE", preferred_date=timezone.localdate() + timedelta(days=1),
        preferred_time="10:00", problem_description="Wellness support", pain_area="Back",
        problem_duration="One week", address="Shastri Nagar", city="Meerut", pin_code="250004",
        landmark="Near park", status=AppointmentRequest.Status.APPROVED,
        final_amount=Decimal(amount), regular_amount=Decimal(amount) + Decimal(discount),
        discount_amount=Decimal(discount), commercial_snapshot=snapshot or {},
    )


def analytics_url(start=None, end=None):
    if start is None:
        return reverse("owner-analytics")
    return f'{reverse("owner-analytics")}?preset=custom&start={start}&end={end}'


def test_owner_only_analytics_and_cross_tenant_scope(api_client):
    values = setup_domain("analytics-security")
    organization, _, owner, manager, physio, _, customer, *_ = values
    for actor in (manager, physio, customer):
        api_client.force_authenticate(actor)
        assert api_client.get(reverse("owner-analytics"), **headers(organization)).status_code == 403
        assert api_client.get(reverse("owner-analytics-csv"), **headers(organization)).status_code == 403
    api_client.force_authenticate(None)
    assert api_client.get(reverse("owner-analytics"), **headers(organization)).status_code == 401
    api_client.force_authenticate(owner)
    response = api_client.get(reverse("owner-analytics"), **headers(organization))
    assert response.status_code == 200
    assert response.data["kpis"]["total_requests"] == 0
    foreign = setup_domain("analytics-foreign")
    api_client.force_authenticate(foreign[2])
    response = api_client.get(reverse("owner-analytics"), **headers(foreign[0]))
    assert response.status_code == 200 and response.data["kpis"]["total_scheduled"] == 0


def test_date_scope_approved_ratings_and_csv(api_client):
    values = setup_domain("analytics-values")
    organization, _, owner, _, _, therapist, customer, *_ = values
    appointment = create_scheduled(api_client, values)
    package_request = make_request(values, amount="7000.00", discount="1400.00", snapshot={"package_id":"historical-id","package_name":"7 Session Plan","final_amount":"7000.00"})
    appointment.originating_request = package_request
    appointment.status = Appointment.Status.COMPLETED
    appointment.assignment_status = Appointment.AssignmentStatus.ACCEPTED
    appointment.completed_at = appointment.scheduled_end
    appointment.save(update_fields=("status", "assignment_status", "completed_at", "originating_request"))
    AppointmentRating.objects.create(appointment=appointment, organization=organization, customer=customer, physiotherapist=therapist, stars=5, comment="Approved", moderation_status=AppointmentRating.ModerationStatus.APPROVED)
    hidden_appointment = create_scheduled(api_client, values, start=start_at(days=2))
    AppointmentRating.objects.create(appointment=hidden_appointment, organization=organization, customer=customer, physiotherapist=therapist, stars=1, moderation_status=AppointmentRating.ModerationStatus.HIDDEN)
    family = CustomerFamilyMember.objects.create(organization=organization, customer=customer, full_name="Meera", age=50, gender="FEMALE", relationship="Mother")
    make_request(values, amount="800.00", discount="200.00", family_member=family)
    PractitionerPayment.objects.create(appointment=appointment, organization=organization, physiotherapist=therapist, payable_amount="500.00", status=PractitionerPayment.Status.PAID, updated_by=owner)
    start = timezone.localdate()
    end = start + timedelta(days=3)
    api_client.force_authenticate(owner)
    response = api_client.get(analytics_url(start, end), **headers(organization))
    assert response.status_code == 200, response.data
    assert response.data["kpis"]["completed"] == 1
    assert response.data["reviews"]["average"] == 5.0
    assert response.data["reviews"]["distribution"]["5"] == 1
    assert response.data["kpis"]["booked_value"] == "7800.00"
    assert response.data["commercial_performance"][0]["name"] == "7 Session Plan"
    assert response.data["commercial_performance"][0]["discounts"] == "1400.00"
    assert response.data["customers"]["total"] == 1 and response.data["customers"]["repeat"] == 1
    assert response.data["customers"]["new"] == 1
    assert response.data["customers"]["family_bookings"] == 1
    assert response.data["practitioner_payments"]["PAID"]["amount"] == "500.00"
    assert response.data["therapists"][0]["completed"] == 1
    today_response = api_client.get(f'{reverse("owner-analytics")}?preset=today', **headers(organization))
    assert today_response.data["kpis"]["total_scheduled"] == 0
    csv_response = api_client.get(f'{reverse("owner-analytics-csv")}?preset=custom&start={start}&end={end}', **headers(organization))
    assert csv_response.status_code == 200
    assert csv_response["Content-Type"].startswith("text/csv")
    assert b"Owner Business Summary" in csv_response.content


def test_invalid_custom_date_range_is_rejected(api_client):
    organization, _, owner, *_ = setup_domain("analytics-range")
    api_client.force_authenticate(owner)
    response = api_client.get(f'{reverse("owner-analytics")}?preset=custom&start=2026-08-20&end=2026-08-01', **headers(organization))
    assert response.status_code == 400
