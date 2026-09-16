import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Notification, Role
from apps.appointments.models import (
    Appointment,
    AppointmentAuditEvent,
    AppointmentPayment,
    AppointmentRating,
)
from tests.test_appointment_operations import create_scheduled
from tests.test_scheduling import add_actor, headers, setup_domain

pytestmark = pytest.mark.django_db


def test_customer_only_rates_once_after_completion(api_client):
    values = setup_domain("rating-flow")
    organization, _, owner, manager, physio_user, _, customer, *_ = values
    appointment = create_scheduled(api_client, values)
    appointment.status = Appointment.Status.COMPLETED
    appointment.assignment_status = Appointment.AssignmentStatus.ACCEPTED
    appointment.completed_at = timezone.now()
    appointment.save(update_fields=("status", "assignment_status", "completed_at"))
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


def test_appointment_payment_is_operations_controlled_and_visible_to_assigned_practitioner(api_client):
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
    assert AppointmentPayment.objects.get(appointment=appointment).updated_by == manager
    api_client.force_authenticate(physio_user)
    listing = api_client.get(reverse("schedule-assigned-me"), **headers(organization))
    item = next(value for value in listing.data if value["id"] == str(appointment.id))
    assert item["payment_status"] == "PAID"
    assert item["payment_paid_at"] is not None


def test_assigned_therapist_atomically_completes_and_confirms_owner_payment_once(
    api_client, django_capture_on_commit_callbacks
):
    values = setup_domain("therapist-owner-payment")
    organization, _, owner, manager, physio_user, _, customer, *_ = values
    appointment = create_scheduled(api_client, values)
    appointment.status = Appointment.Status.IN_PROGRESS
    appointment.assignment_status = Appointment.AssignmentStatus.ACCEPTED
    appointment.journey_status = Appointment.JourneyStatus.REACHED
    appointment.service_started_at = timezone.now()
    appointment.save(
        update_fields=(
            "status",
            "assignment_status",
            "journey_status",
            "service_started_at",
        )
    )
    AppointmentPayment.objects.create(
        appointment=appointment,
        organization=organization,
        amount_due="1777.00",
        updated_by=owner,
    )
    url = reverse("schedule-complete-and-confirm-payment", args=[appointment.id])
    api_client.force_authenticate(physio_user)

    incomplete = api_client.post(
        url,
        {"therapy_delivered": True, "payment_received": False},
        format="json",
        **headers(organization),
    )
    with django_capture_on_commit_callbacks(execute=True):
        result = api_client.post(
            url,
            {"therapy_delivered": True, "payment_received": True},
            format="json",
            **headers(organization),
        )
    duplicate = api_client.post(
        url,
        {"therapy_delivered": True, "payment_received": True},
        format="json",
        **headers(organization),
    )

    appointment.refresh_from_db()
    payment = AppointmentPayment.objects.get(appointment=appointment)
    assert incomplete.status_code == 400
    assert result.status_code == 200
    assert result.data["status"] == Appointment.Status.COMPLETED
    assert result.data["payment_status"] == AppointmentPayment.Status.PAID
    assert result.data["payment_confirmed_by"] == physio_user.get_full_name()
    assert duplicate.status_code == 400
    assert appointment.completed_at and appointment.updated_by == physio_user
    assert payment.paid_at and payment.updated_by == physio_user
    assert appointment.audit_events.filter(
        event=AppointmentAuditEvent.Event.STATUS_CHANGED,
        new_status=Appointment.Status.COMPLETED,
        actor=physio_user,
    ).count() == 1
    completion_notifications = Notification.objects.filter(
        notification_type="THERAPY_COMPLETED_PAYMENT_CONFIRMED"
    )
    assert completion_notifications.filter(recipient=customer).count() == 1
    assert completion_notifications.filter(recipient=owner).count() == 1
    assert completion_notifications.filter(recipient=physio_user).count() == 1
    owner_message = completion_notifications.get(recipient=owner).message
    assert appointment.patient.full_name in owner_message
    assert physio_user.get_full_name() in owner_message
    assert "₹1777.00" in owner_message
    assert appointment.audit_events.filter(
        event=AppointmentAuditEvent.Event.PAYMENT_STATUS_CHANGED,
        previous_status=AppointmentPayment.Status.PENDING,
        new_status=AppointmentPayment.Status.PAID,
        actor=physio_user,
    ).count() == 1

    api_client.force_authenticate(customer)
    customer_items = api_client.get(
        reverse("schedule-customer-me"), **headers(organization)
    )
    customer_item = next(item for item in customer_items.data if item["id"] == str(appointment.id))
    assert customer_item["status"] == Appointment.Status.COMPLETED
    assert customer_item["payment_status"] == AppointmentPayment.Status.PAID

    for actor in (manager, owner):
        api_client.force_authenticate(actor)
        operations = api_client.get(
            reverse("schedule-operations"),
            {"status": Appointment.Status.COMPLETED, "page_size": 100},
            **headers(organization),
        )
        operations_item = next(
            item for item in operations.data["results"] if item["id"] == str(appointment.id)
        )
        assert operations_item["payment_status"] == AppointmentPayment.Status.PAID
        assert operations_item["payment_paid_at"] is not None
        assert operations_item["payment_confirmed_by"] == physio_user.get_full_name()


def test_completion_payment_confirmation_rejects_customer_unassigned_and_cross_tenant_users(api_client):
    values = setup_domain("therapist-payment-policy")
    organization, clinic, owner, _, physio_user, _, customer, *_ = values
    appointment = create_scheduled(api_client, values)
    appointment.status = Appointment.Status.IN_PROGRESS
    appointment.assignment_status = Appointment.AssignmentStatus.ACCEPTED
    appointment.journey_status = Appointment.JourneyStatus.REACHED
    appointment.service_started_at = timezone.now()
    appointment.save(
        update_fields=(
            "status",
            "assignment_status",
            "journey_status",
            "service_started_at",
        )
    )
    AppointmentPayment.objects.create(
        appointment=appointment,
        organization=organization,
        amount_due="1777.00",
        updated_by=owner,
    )
    url = reverse("schedule-complete-and-confirm-payment", args=[appointment.id])
    payload = {"therapy_delivered": True, "payment_received": True}

    api_client.force_authenticate(customer)
    assert api_client.post(
        url, payload, format="json", **headers(organization)
    ).status_code == 403

    other_physio = add_actor(organization, clinic, Role.PHYSIOTHERAPIST, "unassigned-payment")
    api_client.force_authenticate(other_physio)
    assert api_client.post(
        url, payload, format="json", **headers(organization)
    ).status_code == 404

    foreign = setup_domain("therapist-payment-foreign")
    api_client.force_authenticate(foreign[4])
    assert api_client.post(
        url, payload, format="json", **headers(foreign[0])
    ).status_code == 404

    api_client.force_authenticate(physio_user)
    assert api_client.post(
        reverse("schedule-status", args=[appointment.id]),
        {"status": "COMPLETED"},
        format="json",
        **headers(organization),
    ).status_code == 403
    appointment.refresh_from_db()
    assert appointment.status == Appointment.Status.IN_PROGRESS
    assert appointment.payment.status == AppointmentPayment.Status.PENDING


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
    en_route = api_client.post(reverse("schedule-journey", args=[appointment.id]), {"journey_status": "EN_ROUTE"}, format="json", **headers(organization))
    reached = api_client.post(reverse("schedule-journey", args=[appointment.id]), {"journey_status": "REACHED"}, format="json", **headers(organization))
    assert en_route.status_code == 200 and reached.status_code == 200
    api_client.force_authenticate(customer)
    assert api_client.post(reverse("schedule-journey", args=[appointment.id]), {"journey_status": "EN_ROUTE"}, format="json", **headers(organization)).status_code == 403
