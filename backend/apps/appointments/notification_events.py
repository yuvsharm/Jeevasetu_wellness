from django.utils import timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apps.accounts.models import Notification, Role
from apps.accounts.notification_services import notify_owners, notify_user
from apps.appointments.models import Appointment, AppointmentReminder


def _customer(appointment):
    source = appointment.originating_request
    if source and source.creator_id:
        return source.creator
    return appointment.patient.user


def _when(appointment):
    timezone_name = (
        getattr(appointment.clinic, "timezone", "")
        or getattr(appointment.organization, "timezone", "")
        or "Asia/Kolkata"
    )
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("Asia/Kolkata")
    return appointment.scheduled_start.astimezone(zone).strftime("%d %b %Y at %I:%M %p")


def _context(appointment):
    source = appointment.originating_request
    recipient = source.patient_name if source and source.patient_name else appointment.patient.full_name
    return f"{recipient} · {appointment.therapy.name} · {_when(appointment)}"


def notify_booking_request(value):
    common = dict(
        organization=value.organization,
        category=Notification.Category.APPOINTMENTS,
        related_object_type="appointment_request",
        related_object_id=value.id,
    )
    notify_owners(
        **common,
        notification_type="NEW_APPOINTMENT_REQUEST",
        title="New appointment request",
        message=f"{value.patient_name} requested {value.therapy.name} for {value.preferred_date:%d %b %Y}.",
        target_url="/owner#appointment-requests",
        action_required=True,
        dedupe_key=f"appointment-request:{value.id}:created",
    )
    notify_user(
        **common,
        recipient=value.creator,
        recipient_role=Role.CUSTOMER,
        notification_type="BOOKING_RECEIVED",
        title="Booking request received",
        message=f"Your {value.therapy.name} request for {value.preferred_date:%d %b %Y} is awaiting confirmation.",
        target_url="/customer",
        dedupe_key=f"appointment-request:{value.id}:received",
    )


def notify_assignment(appointment):
    if appointment.physiotherapist_id is None:
        return
    context = _context(appointment)
    notify_user(
        organization=appointment.organization,
        recipient=appointment.physiotherapist.user,
        recipient_role=Role.PHYSIOTHERAPIST,
        notification_type="APPOINTMENT_ASSIGNED",
        category=Notification.Category.APPOINTMENTS,
        title="New appointment assignment",
        message=context,
        related_object_type="appointment",
        related_object_id=appointment.id,
        target_url="/physiotherapist/appointments",
        action_required=True,
        dedupe_key=f"appointment:{appointment.id}:assignment:{appointment.assigned_at.isoformat()}",
    )
    notify_user(
        organization=appointment.organization,
        recipient=_customer(appointment),
        recipient_role=Role.CUSTOMER,
        notification_type="THERAPIST_ASSIGNED",
        category=Notification.Category.APPOINTMENTS,
        title="Therapist assigned",
        message=f"A therapist has been assigned for your {_when(appointment)} appointment.",
        related_object_type="appointment",
        related_object_id=appointment.id,
        target_url=f"/customer/appointments/{appointment.id}",
        dedupe_key=f"appointment:{appointment.id}:customer-assignment:{appointment.assigned_at.isoformat()}",
    )


def notify_assignment_response(appointment, *, accepted):
    state = "accepted" if accepted else "declined"
    context = _context(appointment)
    common = dict(
        organization=appointment.organization,
        category=Notification.Category.APPOINTMENTS,
        related_object_type="appointment",
        related_object_id=appointment.id,
        dedupe_key=f"appointment:{appointment.id}:assignment-{state}:{appointment.assignment_responded_at.isoformat()}",
    )
    notify_owners(
        **common,
        notification_type=f"ASSIGNMENT_{state.upper()}",
        title=f"Assignment {state}",
        message=context,
        target_url="/owner/appointments",
        action_required=not accepted,
    )
    if accepted:
        notify_user(
            **common,
            recipient=_customer(appointment),
            recipient_role=Role.CUSTOMER,
            notification_type="APPOINTMENT_CONFIRMED",
            title="Appointment confirmed",
            message=f"Your appointment is confirmed for {_when(appointment)}.",
            target_url=f"/customer/appointments/{appointment.id}",
        )


def notify_unassigned(appointment, *, previous_physiotherapist):
    common = dict(
        organization=appointment.organization,
        category=Notification.Category.APPOINTMENTS,
        notification_type="APPOINTMENT_UNASSIGNED",
        title="Therapist assignment removed",
        related_object_type="appointment",
        related_object_id=appointment.id,
        dedupe_key=f"appointment:{appointment.id}:unassigned:{appointment.updated_at.isoformat()}",
    )
    notify_user(
        **common,
        recipient=previous_physiotherapist.user,
        recipient_role=Role.PHYSIOTHERAPIST,
        message="This visit is no longer assigned to you.",
        target_url="/physiotherapist/appointments",
    )
    notify_user(
        **common,
        recipient=_customer(appointment),
        recipient_role=Role.CUSTOMER,
        message="A replacement therapist is being arranged for your appointment.",
        target_url=f"/customer/appointments/{appointment.id}",
    )


def notify_rescheduled(appointment):
    common = dict(
        organization=appointment.organization,
        category=Notification.Category.APPOINTMENTS,
        notification_type="APPOINTMENT_RESCHEDULED",
        title="Appointment rescheduled",
        message=f"The new time is {_when(appointment)}.",
        related_object_type="appointment",
        related_object_id=appointment.id,
        dedupe_key=f"appointment:{appointment.id}:rescheduled:{appointment.reschedule_count}",
    )
    notify_owners(**common, target_url="/owner/appointments")
    notify_user(**common, recipient=_customer(appointment), recipient_role=Role.CUSTOMER,
                target_url=f"/customer/appointments/{appointment.id}")
    if appointment.physiotherapist_id:
        notify_user(**common, recipient=appointment.physiotherapist.user,
                    recipient_role=Role.PHYSIOTHERAPIST,
                    target_url="/physiotherapist/appointments", action_required=True)


def notify_cancelled(appointment):
    common = dict(
        organization=appointment.organization,
        category=Notification.Category.APPOINTMENTS,
        notification_type="APPOINTMENT_CANCELLED",
        title="Appointment cancelled",
        message=f"The {_when(appointment)} appointment has been cancelled.",
        related_object_type="appointment",
        related_object_id=appointment.id,
        dedupe_key=f"appointment:{appointment.id}:cancelled",
    )
    notify_owners(**common, target_url="/owner/appointments")
    notify_user(**common, recipient=_customer(appointment), recipient_role=Role.CUSTOMER,
                target_url=f"/customer/appointments/{appointment.id}")
    if appointment.physiotherapist_id:
        notify_user(**common, recipient=appointment.physiotherapist.user,
                    recipient_role=Role.PHYSIOTHERAPIST, target_url="/physiotherapist/appointments")


def notify_status_transition(appointment, *, new_status):
    if new_status not in (Appointment.Status.IN_PROGRESS, Appointment.Status.COMPLETED):
        return
    completed = new_status == Appointment.Status.COMPLETED
    common = dict(
        organization=appointment.organization,
        category=Notification.Category.APPOINTMENTS,
        notification_type=f"APPOINTMENT_{new_status}",
        title="Therapy completed" if completed else "Therapy started",
        message=_context(appointment) if completed else f"Your {_when(appointment)} therapy has started.",
        related_object_type="appointment",
        related_object_id=appointment.id,
        dedupe_key=f"appointment:{appointment.id}:status:{new_status}",
    )
    notify_user(**common, recipient=_customer(appointment), recipient_role=Role.CUSTOMER,
                target_url=f"/customer/appointments/{appointment.id}", action_required=completed)
    if completed:
        notify_owners(**common, target_url="/owner/appointments")
        notify_user(
            organization=appointment.organization,
            recipient=_customer(appointment),
            recipient_role=Role.CUSTOMER,
            notification_type="RATING_REMINDER",
            category=Notification.Category.REVIEWS,
            title="Rate your therapist",
            message="Share feedback about your completed therapy session.",
            related_object_type="appointment",
            related_object_id=appointment.id,
            target_url=f"/customer/appointments/{appointment.id}#rating",
            action_required=True,
            dedupe_key=f"appointment:{appointment.id}:rating-reminder",
        )


def notify_reached(appointment):
    common = dict(
        organization=appointment.organization,
        category=Notification.Category.APPOINTMENTS,
        notification_type="THERAPIST_REACHED",
        title="Therapist reached",
        message=f"The therapist has reached for {_context(appointment)}.",
        related_object_type="appointment",
        related_object_id=appointment.id,
        dedupe_key=f"appointment:{appointment.id}:journey:reached",
    )
    notify_owners(**common, target_url="/owner/appointments")
    notify_user(
        **common,
        recipient=_customer(appointment),
        recipient_role=Role.CUSTOMER,
        target_url=f"/customer/appointments/{appointment.id}",
    )


def notify_payment_confirmed(appointment):
    common = dict(
        organization=appointment.organization,
        category=Notification.Category.PAYMENTS,
        notification_type="PAYMENT_CONFIRMED",
        title="Payment confirmed · Appointment booked",
        message=f"Your payment was verified and your appointment is booked for {_when(appointment)}.",
        related_object_type="appointment",
        related_object_id=appointment.id,
        dedupe_key=f"appointment:{appointment.id}:payment:paid",
    )
    notify_user(**common, recipient=_customer(appointment), recipient_role=Role.CUSTOMER,
                target_url=f"/customer/appointments/{appointment.id}")


def notify_payment_submitted(appointment):
    request_id = appointment.originating_request_id
    target_url = (
        f"/owner?request={request_id}#appointment-requests"
        if request_id else "/owner#appointment-requests"
    )
    notify_owners(
        organization=appointment.organization,
        category=Notification.Category.PAYMENTS,
        notification_type="PAYMENT_SUBMITTED",
        title="Payment submitted for verification",
        message=f"{_context(appointment)}.",
        related_object_type="appointment",
        related_object_id=appointment.id,
        target_url=target_url,
        action_required=True,
        dedupe_key=f"appointment:{appointment.id}:payment:verification-pending",
    )


def notify_rating_submitted(rating):
    appointment = rating.appointment
    common = dict(
        organization=rating.organization,
        category=Notification.Category.REVIEWS,
        notification_type="RATING_SUBMITTED",
        title="New customer rating",
        message=f"A {rating.stars}-star rating was submitted for {appointment.therapy.name}.",
        related_object_type="appointment_rating",
        related_object_id=rating.id,
        dedupe_key=f"rating:{rating.id}:submitted",
    )
    notify_owners(**common, target_url="/owner#customer-reviews", action_required=True)
    notify_user(**common, recipient=rating.physiotherapist.user,
                recipient_role=Role.PHYSIOTHERAPIST, target_url="/physiotherapist")


def notify_due_reminder(reminder):
    if reminder.kind != AppointmentReminder.Kind.HOURS_24:
        return
    appointment = reminder.appointment
    common = dict(
        organization=appointment.organization,
        category=Notification.Category.APPOINTMENTS,
        notification_type="APPOINTMENT_REMINDER_24H",
        title="Appointment tomorrow",
        message=_context(appointment),
        related_object_type="appointment_reminder",
        related_object_id=reminder.id,
        dedupe_key=f"appointment-reminder:{reminder.id}:{reminder.scheduled_for.isoformat()}",
    )
    notify_user(**common, recipient=_customer(appointment), recipient_role=Role.CUSTOMER,
                target_url=f"/customer/appointments/{appointment.id}")
    notify_user(**common, recipient=appointment.physiotherapist.user,
                recipient_role=Role.PHYSIOTHERAPIST, target_url="/physiotherapist/appointments")
