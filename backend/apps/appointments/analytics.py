from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Min, Q, Sum
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone

from apps.appointments.models import (
    Appointment,
    AppointmentAuditEvent,
    AppointmentRating,
    AppointmentRequest,
    PractitionerPayment,
)
from apps.practitioners.models import PractitionerApplication
from apps.staff.models import StaffProfile


ZERO = Decimal("0.00")


def resolve_range(params):
    """Return an inclusive local-date scope represented by an exclusive UTC end."""
    today = timezone.localdate()
    preset = params.get("preset", "last_30_days")
    if preset == "today":
        start_day = end_day = today
    elif preset == "last_7_days":
        start_day, end_day = today - timedelta(days=6), today
    elif preset == "this_month":
        start_day, end_day = today.replace(day=1), today
    elif preset == "previous_month":
        current = today.replace(day=1)
        end_day = current - timedelta(days=1)
        start_day = end_day.replace(day=1)
    elif preset == "custom":
        try:
            start_day = date.fromisoformat(params["start"])
            end_day = date.fromisoformat(params["end"])
        except (KeyError, ValueError):
            raise ValueError("Custom range requires valid start and end dates.")
        if end_day < start_day:
            raise ValueError("End date must not precede start date.")
        if (end_day - start_day).days > 366:
            raise ValueError("Analytics ranges may not exceed 366 days.")
    else:
        start_day, end_day = today - timedelta(days=29), today
        preset = "last_30_days"
    zone = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(start_day, time.min), zone)
    end = timezone.make_aware(datetime.combine(end_day + timedelta(days=1), time.min), zone)
    return {"preset": preset, "start_date": start_day, "end_date": end_day, "start": start, "end": end}


def _money(value):
    return str((value or ZERO).quantize(Decimal("0.01")))


def _rate(numerator, denominator):
    return round(numerator * 100 / denominator, 1) if denominator else 0


def build_owner_analytics(organization, scope):
    start, end = scope["start"], scope["end"]
    requests = AppointmentRequest.objects.filter(
        organization=organization, created_at__gte=start, created_at__lt=end
    )
    appointments = Appointment.objects.filter(
        organization=organization, scheduled_start__gte=start, scheduled_start__lt=end
    )
    reviews = AppointmentRating.objects.filter(
        organization=organization,
        moderation_status=AppointmentRating.ModerationStatus.APPROVED,
        created_at__gte=start,
        created_at__lt=end,
    )
    status_counts = dict(
        appointments.values_list("status").annotate(total=Count("id")).values_list("status", "total")
    )
    request_counts = dict(
        requests.values_list("status").annotate(total=Count("id")).values_list("status", "total")
    )
    commercial = requests.aggregate(
        booked=Coalesce(Sum("final_amount"), ZERO), discounts=Coalesce(Sum("discount_amount"), ZERO)
    )
    completed_commercial = requests.filter(
        operational_appointment__status=Appointment.Status.COMPLETED
    ).aggregate(value=Coalesce(Sum("final_amount"), ZERO))["value"]
    completed = status_counts.get(Appointment.Status.COMPLETED, 0)
    cancelled = status_counts.get(Appointment.Status.CANCELLED, 0)
    concluded = completed + cancelled + status_counts.get(Appointment.Status.NO_SHOW, 0)
    measured_services = appointments.filter(
        status=Appointment.Status.COMPLETED,
        service_started_at__isnull=False,
        completed_at__isnull=False,
    ).aggregate(
        actual=Avg(ExpressionWrapper(F("completed_at") - F("service_started_at"), output_field=DurationField())),
        expected=Avg("duration_minutes"),
    )

    customer_counts = list(
        requests.exclude(creator__isnull=True)
        .values("creator_id")
        .annotate(bookings=Count("id"))
        .values_list("bookings", flat=True)
    )
    customers = len(customer_counts)
    repeat_customers = sum(value >= 2 for value in customer_counts)
    new_customers = sum(
        start <= value < end
        for value in AppointmentRequest.objects.filter(
            organization=organization, creator__isnull=False, created_at__lt=end
        ).values("creator_id").annotate(first_booking=Min("created_at")).values_list("first_booking", flat=True)
    )

    approved = reviews.aggregate(average=Avg("stars"), count=Count("id"))
    active_therapists = StaffProfile.objects.filter(
        organization=organization, staff_type="PHYSIOTHERAPIST",
        user__is_active=True, user__is_enabled=True,
    ).count()

    booking_trend = {
        row["day"]: row for row in requests.annotate(day=TruncDate("created_at"))
        .values("day").annotate(bookings=Count("id"), booked_value=Coalesce(Sum("final_amount"), ZERO))
    }
    completed_trend = dict(
        appointments.filter(status=Appointment.Status.COMPLETED)
        .annotate(day=TruncDate("scheduled_start")).values("day")
        .annotate(total=Count("id")).values_list("day", "total")
    )
    customer_trend = dict(
        requests.exclude(creator__isnull=True).annotate(day=TruncDate("created_at"))
        .values("day").annotate(total=Count("creator_id", distinct=True)).values_list("day", "total")
    )
    growth = []
    cursor = scope["start_date"]
    while cursor <= scope["end_date"]:
        row = booking_trend.get(cursor, {})
        growth.append({
            "date": cursor.isoformat(), "bookings": row.get("bookings", 0),
            "completed": completed_trend.get(cursor, 0), "booked_value": _money(row.get("booked_value")),
            "customers": customer_trend.get(cursor, 0),
        })
        cursor += timedelta(days=1)

    payment_rows = PractitionerPayment.objects.filter(
        organization=organization, appointment__scheduled_start__gte=start,
        appointment__scheduled_start__lt=end,
    ).values("status").annotate(count=Count("id"), amount=Coalesce(Sum("payable_amount"), ZERO))
    payments = {choice: {"count": 0, "amount": "0.00"} for choice, _ in PractitionerPayment.Status.choices}
    for row in payment_rows:
        payments[row["status"]] = {"count": row["count"], "amount": _money(row["amount"])}

    # Attribute each booking once per performed therapy. Multi-therapy final value is
    # allocated proportionally from immutable booking-time therapy prices, avoiding
    # both appointment double-counting and today's edited catalog prices.
    approved_by_appointment = dict(reviews.values_list("appointment_id", "stars"))
    therapy_performance = defaultdict(lambda: {"name": "", "bookings": 0, "completed": 0, "booked_value": ZERO, "ratings": []})
    request_rows = requests.values(
        "therapy_id", "therapy__name", "commercial_snapshot", "final_amount",
        "operational_appointment__id", "operational_appointment__status",
    )
    for row in request_rows:
        snapshot = row["commercial_snapshot"] or {}
        ids = [str(value) for value in snapshot.get("therapy_ids", [])] or [str(row["therapy_id"])]
        names = snapshot.get("therapy_names", [])
        prices = snapshot.get("therapy_prices", {})
        weights = [Decimal(str(prices.get(value, 0))) for value in ids]
        weight_total = sum(weights, ZERO)
        final_amount = row["final_amount"] or ZERO
        for index, therapy_id in enumerate(ids):
            item = therapy_performance[therapy_id]
            item["name"] = names[index] if index < len(names) else row["therapy__name"]
            item["bookings"] += 1
            item["completed"] += row["operational_appointment__status"] == Appointment.Status.COMPLETED
            item["booked_value"] += final_amount * weights[index] / weight_total if weight_total else final_amount / len(ids)
            stars = approved_by_appointment.get(row["operational_appointment__id"])
            if stars:
                item["ratings"].append(stars)
    therapies = [{"id": therapy_id, "name": item["name"], "bookings": item["bookings"], "completed": item["completed"], "booked_value": _money(item["booked_value"]), "average_rating": round(sum(item["ratings"]) / len(item["ratings"]), 2) if item["ratings"] else None} for therapy_id, item in therapy_performance.items()]
    therapies.sort(key=lambda item: (-item["bookings"], item["name"]))

    package_offer = defaultdict(lambda: {"bookings": 0, "booked_value": ZERO, "discounts": ZERO, "completed": 0})
    for row in requests.exclude(commercial_snapshot={}).values("commercial_snapshot", "final_amount", "discount_amount", "operational_appointment__status"):
        snapshot = row["commercial_snapshot"] or {}
        if snapshot.get("package_id"):
            key = ("PACKAGE", snapshot.get("package_name") or "Historical package")
        elif snapshot.get("offer_id"):
            key = ("OFFER", snapshot.get("offer_title") or "Historical offer")
        else:
            continue
        item = package_offer[key]
        item["bookings"] += 1
        item["booked_value"] += row["final_amount"] or ZERO
        item["discounts"] += row["discount_amount"] or ZERO
        item["completed"] += row["operational_appointment__status"] == Appointment.Status.COMPLETED
    commercial_performance = []
    for (kind, name), item in package_offer.items():
        commercial_performance.append({"kind": kind, "name": name, "bookings": item["bookings"], "booked_value": _money(item["booked_value"]), "discounts": _money(item["discounts"]), "average_discount": _money(item["discounts"] / item["bookings"]), "completed": item["completed"], "completion_rate": _rate(item["completed"], item["bookings"])})
    commercial_performance.sort(key=lambda item: (-item["bookings"], item["name"]))

    therapist_rows = StaffProfile.objects.filter(organization=organization, staff_type="PHYSIOTHERAPIST").annotate(
        assigned=Count("appointments", filter=Q(appointments__scheduled_start__gte=start, appointments__scheduled_start__lt=end), distinct=True),
        accepted=Count("appointments", filter=Q(appointments__scheduled_start__gte=start, appointments__scheduled_start__lt=end, appointments__assignment_status=Appointment.AssignmentStatus.ACCEPTED), distinct=True),
        completed=Count("appointments", filter=Q(appointments__scheduled_start__gte=start, appointments__scheduled_start__lt=end, appointments__status=Appointment.Status.COMPLETED), distinct=True),
        active_workload=Count("appointments", filter=Q(appointments__scheduled_start__gte=start, appointments__scheduled_start__lt=end, appointments__status__in=Appointment.BLOCKING_STATUSES), distinct=True),
    ).select_related("user")
    rejection_counts = dict(AppointmentAuditEvent.objects.filter(organization=organization, event=AppointmentAuditEvent.Event.ASSIGNMENT_REJECTED, created_at__gte=start, created_at__lt=end).values("previous_physiotherapist_id").annotate(total=Count("id")).values_list("previous_physiotherapist_id", "total"))
    therapist_ratings = {row["physiotherapist_id"]: row for row in reviews.values("physiotherapist_id").annotate(average=Avg("stars"), count=Count("id"))}
    therapists = []
    for row in therapist_rows:
        rating = therapist_ratings.get(row.id, {})
        therapists.append({"id": str(row.id), "name": row.user.get_full_name() or row.user.username, "assigned": row.assigned, "accepted": row.accepted, "rejected": rejection_counts.get(row.id, 0), "completed": row.completed, "active_workload": row.active_workload, "acceptance_rate": _rate(row.accepted, row.assigned), "completion_rate": _rate(row.completed, row.assigned), "average_rating": round(rating["average"], 2) if rating.get("average") else None, "review_count": rating.get("count", 0)})

    distribution = {str(star): 0 for star in range(1, 6)}
    for stars, total in reviews.values_list("stars").annotate(total=Count("id")).values_list("stars", "total"):
        distribution[str(stars)] = total
    rating_trend = [{"date": row["day"].isoformat(), "average": round(row["average"], 2), "count": row["count"]} for row in reviews.annotate(day=TruncDate("created_at")).values("day").annotate(average=Avg("stars"), count=Count("id")).order_by("day")]
    recent_reviews = [{"stars": row.stars, "comment": row.comment, "created_at": row.created_at.isoformat(), "therapy": row.appointment.therapy.name} for row in reviews.select_related("appointment__therapy").order_by("-created_at")[:5]]

    overdue = appointments.filter(status__in=Appointment.BLOCKING_STATUSES, scheduled_end__lt=timezone.now()).count()
    attention = {
        "pending_requests": request_counts.get(AppointmentRequest.Status.PENDING, 0),
        "awaiting_therapist": appointments.filter(Q(physiotherapist__isnull=True) | Q(assignment_status__in=(Appointment.AssignmentStatus.UNASSIGNED, Appointment.AssignmentStatus.REJECTED))).exclude(status__in=Appointment.FINAL_STATUSES).count(),
        "therapist_rejections": AppointmentAuditEvent.objects.filter(organization=organization, event=AppointmentAuditEvent.Event.ASSIGNMENT_REJECTED, created_at__gte=start, created_at__lt=end).count(),
        "overdue_appointments": overdue,
        "pending_practitioner_payments": payments[PractitionerPayment.Status.PENDING]["count"],
        "pending_review_moderation": AppointmentRating.objects.filter(organization=organization, moderation_status=AppointmentRating.ModerationStatus.PENDING, created_at__gte=start, created_at__lt=end).count(),
        "pending_practitioner_applications": PractitionerApplication.objects.filter(organization=organization, status__in=(PractitionerApplication.Status.SUBMITTED, PractitionerApplication.Status.UNDER_REVIEW), created_at__gte=start, created_at__lt=end).count(),
    }
    return {
        "scope": {"preset": scope["preset"], "start_date": scope["start_date"].isoformat(), "end_date": scope["end_date"].isoformat(), "timezone": str(timezone.get_current_timezone())},
        "definitions": {"booked_value": "Booking-time final amounts from appointment request commercial snapshots.", "repeat_customer": "A customer account with at least two requests in the selected period.", "payment_position": "Practitioner payout records; not customer collections or gateway settlement."},
        "kpis": {"total_requests": requests.count(), "total_scheduled": appointments.count(), "pending": status_counts.get(Appointment.Status.PENDING_ASSIGNMENT, 0), "confirmed": status_counts.get(Appointment.Status.CONFIRMED, 0), "in_progress": status_counts.get(Appointment.Status.IN_PROGRESS, 0), "completed": completed, "cancelled": cancelled, "customers": customers, "repeat_customers": repeat_customers, "active_therapists": active_therapists, "average_approved_rating": round(approved["average"], 2) if approved["average"] else None, "booked_value": _money(commercial["booked"]), "completed_service_value": _money(completed_commercial), "total_discounts": _money(commercial["discounts"])},
        "appointments": {"request_statuses": request_counts, "statuses": status_counts, "completion_rate": _rate(completed, concluded), "cancellation_rate": _rate(cancelled, concluded), "average_actual_service_minutes": round(measured_services["actual"].total_seconds() / 60, 1) if measured_services["actual"] else None, "average_expected_service_minutes": round(measured_services["expected"], 1) if measured_services["expected"] else None},
        "growth": growth, "practitioner_payments": payments, "therapies": therapies,
        "commercial_performance": commercial_performance,
        "customers": {"total": customers, "new": new_customers, "repeat": repeat_customers, "repeat_rate": _rate(repeat_customers, customers), "self_bookings": requests.filter(family_member__isnull=True).count(), "family_bookings": requests.filter(family_member__isnull=False).count(), "average_completed_per_returning_customer": round(appointments.filter(status=Appointment.Status.COMPLETED, originating_request__creator__in=requests.exclude(creator__isnull=True).values("creator_id")).count() / repeat_customers, 2) if repeat_customers else 0},
        "therapists": therapists,
        "reviews": {"average": round(approved["average"], 2) if approved["average"] else None, "count": approved["count"], "distribution": distribution, "trend": rating_trend, "recent": recent_reviews},
        "attention": attention,
    }
