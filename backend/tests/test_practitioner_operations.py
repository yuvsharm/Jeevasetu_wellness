import pytest
from django.urls import reverse

from apps.appointments.models import Appointment, AppointmentRating, PractitionerPayment
from tests.test_appointment_operations import create_scheduled
from tests.test_scheduling import headers, setup_domain

pytestmark = pytest.mark.django_db


def test_customer_only_rates_once_after_completion(api_client):
    values = setup_domain("rating-flow")
    organization, _, owner, manager, physio_user, _, customer, *_ = values
    appointment = create_scheduled(api_client, values)
    appointment.status = Appointment.Status.COMPLETED
    appointment.assignment_status = Appointment.AssignmentStatus.ACCEPTED
    appointment.save(update_fields=("status", "assignment_status"))
    url = reverse("schedule-customer-rating", args=[appointment.id])
    api_client.force_authenticate(physio_user)
    assert api_client.post(url, {"stars": 5}, format="json", **headers(organization)).status_code == 403
    api_client.force_authenticate(customer)
    assert api_client.post(url, {"stars": 5, "comment": "Professional service"}, format="json", **headers(organization)).status_code == 201
    assert api_client.post(url, {"stars": 4}, format="json", **headers(organization)).status_code == 400
    assert AppointmentRating.objects.filter(appointment=appointment, customer=customer).count() == 1


def test_rating_before_completion_and_cross_tenant_are_denied(api_client):
    values = setup_domain("rating-policy")
    organization, _, _, _, _, _, customer, *_ = values
    appointment = create_scheduled(api_client, values)
    api_client.force_authenticate(customer)
    assert api_client.post(reverse("schedule-customer-rating", args=[appointment.id]), {"stars": 5}, format="json", **headers(organization)).status_code == 404
    foreign = setup_domain("rating-foreign")
    foreign_customer = foreign[6]
    api_client.force_authenticate(foreign_customer)
    assert api_client.post(reverse("schedule-customer-rating", args=[appointment.id]), {"stars": 5}, format="json", **headers(foreign[0])).status_code == 404


def test_payment_is_operations_controlled_and_visible_to_assigned_practitioner(api_client):
    values = setup_domain("payment-flow")
    organization, _, _, manager, physio_user, _, _, *_ = values
    appointment = create_scheduled(api_client, values)
    appointment.status = Appointment.Status.COMPLETED
    appointment.save(update_fields=("status",))
    url = reverse("schedule-operations-payment", args=[appointment.id])
    api_client.force_authenticate(physio_user)
    assert api_client.post(url, {"status": "PAID"}, format="json", **headers(organization)).status_code == 403
    api_client.force_authenticate(manager)
    updated = api_client.post(url, {"status": "PAID", "reference": "BANK-42"}, format="json", **headers(organization))
    assert updated.status_code == 200 and updated.data["status"] == "PAID"
    api_client.force_authenticate(physio_user)
    listing = api_client.get(reverse("schedule-practitioner-payments"), **headers(organization))
    assert listing.status_code == 200 and listing.data[0]["reference"] == "BANK-42"
    assert PractitionerPayment.objects.get(appointment=appointment).updated_by == manager


def test_offer_hides_patient_details_until_acceptance_and_journey_is_owned(api_client):
    values = setup_domain("journey-flow")
    organization, _, _, _, physio_user, _, customer, *_ = values
    appointment = create_scheduled(api_client, values)
    api_client.force_authenticate(physio_user)
    before = api_client.get(reverse("schedule-assigned-me"), **headers(organization))
    offer = next(item for item in before.data if item["id"] == str(appointment.id))
    assert offer["patient_name"] == "Service request"
    assert offer["patient_mobile"] == "" and offer["address_line_1"] == ""
    api_client.post(reverse("schedule-assignment-response", args=[appointment.id]), {"accept": True}, format="json", **headers(organization))
    after = api_client.get(reverse("schedule-assigned-me"), **headers(organization))
    accepted = next(item for item in after.data if item["id"] == str(appointment.id))
    assert accepted["patient_name"] == appointment.patient.full_name
    en_route = api_client.post(reverse("schedule-journey", args=[appointment.id]), {"journey_status": "EN_ROUTE", "latitude": "28.613900", "longitude": "77.209000"}, format="json", **headers(organization))
    arrived = api_client.post(reverse("schedule-journey", args=[appointment.id]), {"journey_status": "ARRIVED"}, format="json", **headers(organization))
    assert en_route.status_code == 200 and arrived.status_code == 200
    api_client.force_authenticate(customer)
    assert api_client.post(reverse("schedule-journey", args=[appointment.id]), {"journey_status": "ARRIVED"}, format="json", **headers(organization)).status_code == 403
