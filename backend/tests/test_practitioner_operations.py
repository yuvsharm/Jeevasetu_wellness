from datetime import time, timedelta

import pytest

from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Notification, Role
from apps.appointments.models import (
    Appointment,
    AppointmentAuditEvent,
    AppointmentPayment,
    AppointmentRating,
    AppointmentRequest,
)
from apps.patients.models import CustomerFamilyMember
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


def test_completion_creates_missing_payment_and_enables_one_time_customer_rating(
    api_client, django_capture_on_commit_callbacks
):
    values = setup_domain("completion-rating-regression")
    organization, _, owner, _, physio_user, _, customer, *_ = values
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
    assert not AppointmentPayment.objects.filter(appointment=appointment).exists()

    api_client.force_authenticate(physio_user)
    with django_capture_on_commit_callbacks(execute=True):
        completed = api_client.post(
            reverse("schedule-complete-and-confirm-payment", args=[appointment.id]),
            {"therapy_delivered": True, "payment_received": True},
            format="json",
            **headers(organization),
        )

    appointment.refresh_from_db()
    payment = AppointmentPayment.objects.get(appointment=appointment)
    assert completed.status_code == 200
    assert appointment.status == Appointment.Status.COMPLETED
    assert appointment.completed_at is not None
    assert payment.status == AppointmentPayment.Status.PAID
    assert payment.paid_at is not None
    notifications = Notification.objects.filter(
        related_object_id=appointment.id,
        notification_type="THERAPY_COMPLETED_PAYMENT_CONFIRMED",
    )
    assert notifications.filter(recipient=customer).count() == 1
    assert notifications.filter(recipient=owner).count() == 1
    assert notifications.filter(recipient=physio_user).count() == 1
    rating_reminder = Notification.objects.get(
        related_object_id=appointment.id,
        notification_type="RATING_REMINDER",
        recipient=customer,
    )
    assert rating_reminder.target_url == f"/customer/appointments/{appointment.id}#rating"

    api_client.force_authenticate(customer)
    customer_items = api_client.get(
        reverse("schedule-customer-me"), **headers(organization)
    )
    customer_item = next(item for item in customer_items.data if item["id"] == str(appointment.id))
    assert customer_item["status"] == Appointment.Status.COMPLETED
    assert customer_item["rating"] is None
    rating_url = reverse("schedule-customer-rating", args=[appointment.id])
    assert api_client.post(
        rating_url,
        {"stars": 5, "comment": ""},
        format="json",
        **headers(organization),
    ).status_code == 201
    assert api_client.post(
        rating_url,
        {"stars": 4, "comment": "Duplicate rating"},
        format="json",
        **headers(organization),
    ).status_code == 400
    assert AppointmentRating.objects.filter(
        appointment=appointment,
        customer=customer,
        physiotherapist=appointment.physiotherapist,
    ).count() == 1


def test_offer_shows_service_details_before_acceptance_and_journey_is_owned(api_client):
    values = setup_domain("journey-flow")
    organization, _, _, _, physio_user, _, customer, *_ = values
    appointment = create_scheduled(api_client, values)
    api_client.force_authenticate(physio_user)
    before = api_client.get(reverse("schedule-assigned-me"), **headers(organization))
    offer = next(item for item in before.data if item["id"] == str(appointment.id))
    assert offer["patient_name"] == appointment.patient.full_name
    assert offer["patient_mobile"] == appointment.patient.mobile_number
    assert offer["address_line_1"] == appointment.address_line_1
    api_client.post(reverse("schedule-assignment-response", args=[appointment.id]), {"accept": True}, format="json", **headers(organization))
    after = api_client.get(reverse("schedule-assigned-me"), **headers(organization))
    accepted = next(item for item in after.data if item["id"] == str(appointment.id))
    assert accepted["patient_name"] == appointment.patient.full_name
    en_route = api_client.post(reverse("schedule-journey", args=[appointment.id]), {"journey_status": "EN_ROUTE"}, format="json", **headers(organization))
    reached = api_client.post(reverse("schedule-journey", args=[appointment.id]), {"journey_status": "REACHED"}, format="json", **headers(organization))
    assert en_route.status_code == 200 and reached.status_code == 200
    api_client.force_authenticate(customer)
    assert api_client.post(reverse("schedule-journey", args=[appointment.id]), {"journey_status": "EN_ROUTE"}, format="json", **headers(organization)).status_code == 403


def test_owner_and_assigned_therapist_use_booking_recipient_contact_and_address_without_mixing(api_client):
    values = setup_domain("booking-recipient-identity")
    organization, clinic, owner, _, physio_user, physio, customer, patient, _, therapy = values
    family = CustomerFamilyMember.objects.create(
        organization=organization,
        customer=customer,
        full_name="Meera Relative",
        age=67,
        gender="FEMALE",
        relationship="Mother",
    )

    def make_booking(*, recipient_name, recipient_age, family_member, day_offset, address_line):
        preferred_date = timezone.localdate() + timedelta(days=day_offset)
        source = AppointmentRequest.objects.create(
            organization=organization,
            creator=customer,
            patient_profile=patient,
            family_member=family_member,
            therapy=therapy,
            patient_name=recipient_name,
            age=recipient_age,
            gender="FEMALE",
            mobile_number=patient.mobile_number,
            session_preference=AppointmentRequest.SessionPreference.SINGLE,
            preferred_date=preferred_date,
            preferred_time=time(10),
            address=address_line,
            landmark="Near canonical landmark",
            city="Meerut",
            region="Uttar Pradesh",
            pin_code="250004",
            status=AppointmentRequest.Status.APPROVED,
        )
        start = timezone.now() + timedelta(days=day_offset)
        return source, Appointment.objects.create(
            organization=organization,
            clinic=clinic,
            originating_request=source,
            patient=patient,
            therapy=therapy,
            physiotherapist=physio,
            scheduled_start=start,
            scheduled_end=start + timedelta(minutes=45),
            duration_minutes=45,
            status=Appointment.Status.SCHEDULED,
            assignment_status=Appointment.AssignmentStatus.PENDING,
            address_line_1=address_line,
            landmark="Near canonical landmark",
            city="Meerut",
            region="Uttar Pradesh",
            pin_code="250004",
            assigned_by=owner,
            assigned_at=timezone.now(),
            created_by=owner,
            updated_by=owner,
        )

    _, self_appointment = make_booking(
        recipient_name=patient.full_name,
        recipient_age=patient.age,
        family_member=None,
        day_offset=2,
        address_line="Self visit address",
    )
    family_source, family_appointment = make_booking(
        recipient_name=family.full_name,
        recipient_age=family.age,
        family_member=family,
        day_offset=3,
        address_line="Family visit address",
    )

    api_client.force_authenticate(owner)
    owner_list = api_client.get(reverse("appointment-owner-list"), **headers(organization))
    owner_family = next(
        item for item in owner_list.data["results"] if item["id"] == str(family_source.id)
    )
    assert owner_family["patient_name"] == family.full_name
    assert owner_family["mobile_number"] == patient.mobile_number
    assert owner_family["address"] == "Family visit address"

    api_client.force_authenticate(physio_user)
    pending = api_client.get(reverse("schedule-assigned-me"), **headers(organization))
    self_item = next(item for item in pending.data if item["id"] == str(self_appointment.id))
    family_item = next(item for item in pending.data if item["id"] == str(family_appointment.id))
    assert self_item["patient_name"] == patient.full_name
    assert family_item["patient_name"] == family.full_name
    assert family_item["patient_name"] != patient.full_name
    assert self_item["patient_mobile"] == family_item["patient_mobile"] == patient.mobile_number
    assert self_item["address_line_1"] == "Self visit address"
    assert family_item["address_line_1"] == "Family visit address"
    assert family_item["patient_age"] == family.age

    for status in (
        Appointment.Status.CONFIRMED,
        Appointment.Status.IN_PROGRESS,
        Appointment.Status.COMPLETED,
    ):
        Appointment.objects.filter(pk=family_appointment.pk).update(
            assignment_status=Appointment.AssignmentStatus.ACCEPTED,
            status=status,
        )
        state = api_client.get(reverse("schedule-assigned-me"), **headers(organization))
        item = next(value for value in state.data if value["id"] == str(family_appointment.id))
        assert item["patient_name"] == family.full_name
        assert item["patient_mobile"] == patient.mobile_number
        assert item["address_line_1"] == "Family visit address"

    unrelated_user = add_actor(organization, clinic, Role.PHYSIOTHERAPIST, "unrelated-identity")
    api_client.force_authenticate(unrelated_user)
    unrelated = api_client.get(reverse("schedule-assigned-me"), **headers(organization))
    assert unrelated.status_code == 200 and unrelated.data == []

    foreign_organization = setup_domain("booking-recipient-foreign")[0]
    api_client.force_authenticate(physio_user)
    cross_tenant = api_client.get(
        reverse("schedule-assigned-me"), **headers(foreign_organization)
    )
    assert cross_tenant.status_code == 403
