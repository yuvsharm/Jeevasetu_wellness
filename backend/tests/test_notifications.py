from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Notification, Role
from apps.accounts.notification_services import notify_user
from apps.appointments.models import Appointment, AppointmentRating, AppointmentReminder
from apps.appointments.notification_events import (
    notify_cancelled,
    notify_payment_confirmed,
    notify_rating_submitted,
    notify_reached,
    notify_rescheduled,
    notify_status_transition,
)
from apps.appointments.tasks import dispatch_due_appointment_reminders
from apps.practitioners.services import approve_application, review_application, submit_application
from tests.test_appointment_operations import create_scheduled
from tests.test_appointments import authenticated_payload, setup_identity, tenant
from tests.test_practitioners import application as practitioner_application
from tests.test_practitioners import identity as practitioner_identity
from tests.test_scheduling import headers, setup_domain
from apps.appointments.models import TherapyOption
from apps.tenancy.models import Clinic, Organization

pytestmark = pytest.mark.django_db(transaction=True)


def create_notification(organization, recipient, role, *, key="test:one", category="APPOINTMENTS"):
    return Notification.objects.create(
        organization=organization,
        recipient=recipient,
        recipient_role=role,
        notification_type="TEST_EVENT",
        category=category,
        title="Test notification",
        message="Minimum safe context",
        related_object_type="test",
        related_object_id="one",
        target_url="/customer",
        dedupe_key=key,
    )


def test_list_and_bell_count_do_not_mark_notifications_read(api_client):
    organization, _, owner, *_ = setup_domain("notification-list")
    value = create_notification(organization, owner, Role.OWNER)
    historical = create_notification(
        organization, owner, Role.OWNER, key="test:read-history"
    )
    historical.read_at = timezone.now()
    historical.save(update_fields=("read_at",))
    api_client.force_authenticate(owner)

    count = api_client.get(reverse("notification-unread-count"), {"role": Role.OWNER}, **headers(organization))
    listing = api_client.get(reverse("notification-list"), {"role": Role.OWNER}, **headers(organization))

    value.refresh_from_db()
    assert count.status_code == 200 and count.data["unread_count"] == 1
    assert listing.status_code == 200 and listing.data["count"] == 1
    assert [item["id"] for item in listing.data["results"]] == [str(value.id)]
    assert value.read_at is None


def test_individual_read_persists_and_does_not_clear_another_notification(api_client):
    organization, _, owner, *_ = setup_domain("notification-read")
    first = create_notification(organization, owner, Role.OWNER, key="read:first")
    second = create_notification(organization, owner, Role.OWNER, key="read:second")
    api_client.force_authenticate(owner)

    response = api_client.post(f'{reverse("notification-read", args=[first.id])}?role={Role.OWNER}', **headers(organization))
    first.refresh_from_db()
    second.refresh_from_db()

    assert response.status_code == 200 and response.data["is_read"] is True
    assert first.read_at is not None and second.read_at is None
    listing = api_client.get(
        reverse("notification-list"), {"role": Role.OWNER}, **headers(organization)
    )
    assert [item["id"] for item in listing.data["results"]] == [str(second.id)]


def test_notification_access_is_user_role_and_tenant_scoped(api_client):
    organization, _, owner, _, _, _, customer, *_ = setup_domain("notification-scope")
    foreign = setup_domain("notification-scope-foreign")
    value = create_notification(organization, owner, Role.OWNER)

    api_client.force_authenticate(customer)
    assert api_client.get(reverse("notification-list"), {"role": Role.OWNER}, **headers(organization)).status_code == 403
    assert api_client.post(f'{reverse("notification-read", args=[value.id])}?role={Role.CUSTOMER}', **headers(organization)).status_code == 404
    api_client.force_authenticate(foreign[2])
    assert api_client.get(reverse("notification-list"), {"role": Role.OWNER}, **headers(organization)).status_code == 403


def test_dedupe_key_and_rollback_prevent_duplicate_or_orphan_notifications():
    organization, _, owner, *_ = setup_domain("notification-dedupe")
    payload = dict(
        organization=organization, recipient=owner, recipient_role=Role.OWNER,
        notification_type="SAFE", category=Notification.Category.APPOINTMENTS,
        title="Safe", message="Safe", related_object_type="appointment",
        related_object_id="one", target_url="/owner", dedupe_key="stable:event:one",
    )
    notify_user(**payload)
    notify_user(**payload)
    assert Notification.objects.filter(recipient=owner, dedupe_key="stable:event:one").count() == 1

    with pytest.raises(RuntimeError):
        with transaction.atomic():
            notify_user(**{**payload, "dedupe_key": "rolled-back:event"})
            raise RuntimeError("rollback")
    assert not Notification.objects.filter(dedupe_key="rolled-back:event").exists()


def test_notification_persistence_failure_does_not_rollback_business_state(monkeypatch):
    organization, _, owner, *_ = setup_domain("notification-failure-isolation")

    def fail_to_persist(*args, **kwargs):
        raise RuntimeError("notification storage unavailable")

    monkeypatch.setattr(Notification.objects, "get_or_create", fail_to_persist)
    with transaction.atomic():
        owner.first_name = "Business state committed"
        owner.save(update_fields=("first_name",))
        notify_user(
            organization=organization, recipient=owner, recipient_role=Role.OWNER,
            notification_type="SAFE", category=Notification.Category.APPOINTMENTS,
            title="Safe", message="Safe", related_object_type="appointment",
            related_object_id="failure", target_url="/owner", dedupe_key="failure:isolation",
        )

    owner.refresh_from_db()
    assert owner.first_name == "Business state committed"
    assert not Notification.objects.filter(dedupe_key="failure:isolation").exists()


def test_customer_booking_creates_customer_notification_only_after_success(api_client):
    organization, customer, therapy = setup_identity(Role.CUSTOMER)
    api_client.force_authenticate(customer)
    url = reverse("quick-appointment-create")
    created = api_client.post(url, authenticated_payload(therapy), format="json", **tenant(organization.slug))
    duplicate = api_client.post(url, authenticated_payload(therapy), format="json", **tenant(organization.slug))

    assert created.status_code == 201 and duplicate.status_code == 400
    assert Notification.objects.filter(recipient=customer, notification_type="BOOKING_RECEIVED").count() == 1


def test_assignment_and_response_emit_intended_role_notifications(api_client):
    values = setup_domain("notification-assignment")
    organization, _, owner, _, physio_user, _, customer, *_ = values
    appointment = create_scheduled(api_client, values)
    assert Notification.objects.filter(recipient=physio_user, notification_type="APPOINTMENT_ASSIGNED").count() == 1
    assert Notification.objects.filter(recipient=customer, notification_type="THERAPIST_ASSIGNED").count() == 1

    api_client.force_authenticate(physio_user)
    accepted = api_client.post(reverse("schedule-assignment-response", args=[appointment.id]), {"accept": True}, format="json", **headers(organization))
    assert accepted.status_code == 200
    assert Notification.objects.filter(recipient=owner, notification_type="ASSIGNMENT_ACCEPTED").count() == 1
    assert Notification.objects.filter(recipient=customer, notification_type="APPOINTMENT_CONFIRMED").count() == 1

    declined_values = setup_domain("notification-assignment-declined")
    declined_organization, _, declined_owner, _, declined_physio, *_ = declined_values
    declined_appointment = create_scheduled(api_client, declined_values)
    api_client.force_authenticate(declined_physio)
    declined = api_client.post(
        reverse("schedule-assignment-response", args=[declined_appointment.id]),
        {"accept": False, "reason": "Unavailable for this visit"},
        format="json", **headers(declined_organization),
    )
    assert declined.status_code == 200
    assert Notification.objects.filter(recipient=declined_owner, notification_type="ASSIGNMENT_DECLINED").count() == 1


def test_reschedule_cancel_status_payment_and_rating_event_notifications():
    values = setup_domain("notification-events")
    organization, _, owner, _, _, physio, customer, *_ = values
    # Build through the tested API helper without hiding these event-specific assertions.
    from rest_framework.test import APIClient
    appointment = create_scheduled(APIClient(), values)
    appointment.reschedule_count = 1
    notify_rescheduled(appointment)
    notify_cancelled(appointment)
    notify_status_transition(appointment, new_status=Appointment.Status.IN_PROGRESS)
    notify_status_transition(appointment, new_status=Appointment.Status.COMPLETED)
    notify_payment_confirmed(appointment)
    rating = AppointmentRating.objects.create(
        appointment=appointment, organization=organization, customer=customer,
        physiotherapist=physio, stars=5, comment="Professional care",
    )
    notify_rating_submitted(rating)

    assert Notification.objects.filter(recipient=owner, notification_type="APPOINTMENT_RESCHEDULED").exists()
    assert Notification.objects.filter(recipient=customer, notification_type="APPOINTMENT_CANCELLED").exists()
    assert Notification.objects.filter(recipient=customer, notification_type="APPOINTMENT_IN_PROGRESS").exists()
    assert Notification.objects.filter(recipient=owner, notification_type="APPOINTMENT_COMPLETED").exists()
    assert Notification.objects.filter(recipient=physio.user, notification_type="PAYMENT_CONFIRMED").exists()
    assert Notification.objects.filter(recipient=physio.user, notification_type="RATING_SUBMITTED").exists()


def test_reached_notifies_owner_and_customer_once_with_local_event_time():
    values = setup_domain("notification-reached")
    organization, _, owner, _, _, _, customer, *_ = values
    from rest_framework.test import APIClient

    appointment = create_scheduled(APIClient(), values)
    appointment.scheduled_start = datetime(2026, 9, 24, 11, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    appointment.save(update_fields=("scheduled_start",))

    notify_reached(appointment)
    notify_reached(appointment)

    reached = Notification.objects.filter(notification_type="THERAPIST_REACHED")
    assert reached.filter(recipient=owner).count() == 1
    assert reached.filter(recipient=customer).count() == 1
    assert all("24 Sep 2026 at 11:00 AM" in value.message for value in reached)
    assert not any("05:30 AM" in value.message for value in reached)


def test_due_24_hour_reminder_is_idempotent_for_customer_and_therapist(api_client):
    values = setup_domain("notification-reminder")
    _, _, _, _, physio_user, physio, customer, *_ = values
    appointment = create_scheduled(api_client, values)
    appointment.status = Appointment.Status.CONFIRMED
    appointment.assignment_status = Appointment.AssignmentStatus.ACCEPTED
    appointment.scheduled_start = timezone.now() + timedelta(hours=23)
    appointment.scheduled_end = appointment.scheduled_start + timedelta(minutes=45)
    appointment.save(update_fields=("status", "assignment_status", "scheduled_start", "scheduled_end"))
    reminder = AppointmentReminder.objects.create(
        appointment=appointment, practitioner=physio, kind=AppointmentReminder.Kind.HOURS_24,
        scheduled_for=timezone.now() - timedelta(minutes=1),
    )

    assert dispatch_due_appointment_reminders() == 1
    assert dispatch_due_appointment_reminders() == 0
    reminder.refresh_from_db()
    assert reminder.status == AppointmentReminder.Status.SENT
    assert Notification.objects.filter(notification_type="APPOINTMENT_REMINDER_24H", recipient__in=(customer, physio_user)).count() == 2


def practitioner_domain(slug):
    organization = Organization.objects.create(legal_name=slug, display_name=slug, slug=slug)
    clinic = Clinic.objects.create(organization=organization, name="Meerut", slug="meerut")
    therapy = TherapyOption.objects.create(organization=organization, name="Physiotherapy", slug="physiotherapy")
    applicant = practitioner_identity(organization, f"applicant-{slug}", role=None)
    manager = practitioner_identity(organization, f"manager-{slug}", Role.MANAGER, clinic)
    owner = practitioner_identity(organization, f"owner-{slug}", Role.OWNER)
    return organization, clinic, therapy, applicant, manager, owner


def test_practitioner_submission_and_correction_notifications_are_visible_to_roleless_applicant(api_client):
    domain = practitioner_domain("notification-application")
    organization, _, _, applicant, _, owner = domain
    value = practitioner_application(domain)
    submit_application(value, actor=applicant)
    review_application(value, actor=owner, action="review")
    review_application(value, actor=owner, action="correction", reason="Upload a clearer qualification document")

    assert Notification.objects.filter(recipient=owner, notification_type="PRACTITIONER_APPLICATION_SUBMITTED").exists()
    assert Notification.objects.filter(recipient=applicant, notification_type="APPLICATION_RECEIVED").exists()
    assert Notification.objects.filter(recipient=applicant, notification_type="APPLICATION_CORRECTION_REQUIRED").exists()
    api_client.force_authenticate(applicant)
    listing = api_client.get(reverse("notification-list"), {"role": Role.PHYSIOTHERAPIST}, **headers(organization))
    assert listing.status_code == 200 and listing.data["unread_count"] == 2


def test_practitioner_approval_and_rejection_notifications():
    rejected_domain = practitioner_domain("notification-application-rejected")
    rejected = practitioner_application(rejected_domain)
    submit_application(rejected, actor=rejected_domain[3])
    review_application(rejected, actor=rejected_domain[5], action="review")
    review_application(rejected, actor=rejected_domain[5], action="reject", reason="Credentials could not be verified")
    assert Notification.objects.filter(recipient=rejected_domain[3], notification_type="APPLICATION_REJECTED").exists()

    approved_domain = practitioner_domain("notification-application-approved")
    approved = practitioner_application(approved_domain)
    approved.documents.update(verification_status="VERIFIED")
    submit_application(approved, actor=approved_domain[3])
    review_application(approved, actor=approved_domain[5], action="review")
    approve_application(approved, actor=approved_domain[5])
    assert Notification.objects.filter(recipient=approved_domain[3], notification_type="APPLICATION_APPROVED").exists()
