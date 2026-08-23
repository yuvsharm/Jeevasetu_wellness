import pytest
from django.urls import reverse
from django.utils import timezone

from apps.appointments.models import Appointment, AppointmentRating, AppointmentRatingModerationEvent
from tests.test_appointment_operations import create_scheduled
from tests.test_scheduling import headers, setup_domain

pytestmark = pytest.mark.django_db


def completed_appointment(api_client, values):
    appointment = create_scheduled(api_client, values)
    appointment.status = Appointment.Status.COMPLETED
    appointment.assignment_status = Appointment.AssignmentStatus.ACCEPTED
    appointment.completed_at = timezone.now()
    appointment.save(update_fields=("status", "assignment_status", "completed_at"))
    return appointment


def submit_review(api_client, values, stars=5, comment="Excellent and professional service"):
    organization, _, _, _, _, _, customer, *_ = values
    appointment = completed_appointment(api_client, values)
    api_client.force_authenticate(customer)
    response = api_client.post(reverse("schedule-customer-rating", args=[appointment.id]), {"stars": stars, "comment": comment}, format="json", **headers(organization))
    assert response.status_code == 201
    return appointment, AppointmentRating.objects.get(appointment=appointment)


def test_review_requires_completed_owned_appointment_and_valid_comment(api_client):
    values = setup_domain("review-eligibility")
    organization, _, _, manager, _, _, customer, *_ = values
    appointment = create_scheduled(api_client, values)
    api_client.force_authenticate(customer)
    url = reverse("schedule-customer-rating", args=[appointment.id])
    assert api_client.post(url, {"stars": 5, "comment": "Great"}, format="json", **headers(organization)).status_code == 404
    appointment.status = Appointment.Status.COMPLETED
    appointment.completed_at = timezone.now()
    appointment.save(update_fields=("status", "completed_at"))
    assert api_client.post(url, {"stars": 5, "comment": "x"}, format="json", **headers(organization)).status_code == 400
    api_client.force_authenticate(manager)
    assert api_client.post(url, {"stars": 5, "comment": "Fabricated review"}, format="json", **headers(organization)).status_code == 403


def test_moderation_is_scoped_audited_and_public_is_approved_only(api_client):
    values = setup_domain("review-moderation")
    organization, _, owner, manager, physio_user, _, customer, *_ = values
    appointment, review = submit_review(api_client, values)
    public_url = reverse("reviews-public")
    api_client.force_authenticate(None)
    assert api_client.get(public_url, **headers(organization)).data["review_count"] == 0
    api_client.force_authenticate(customer)
    assert api_client.post(reverse("reviews-moderate", args=[review.id]), {"moderation_status": "APPROVED"}, format="json", **headers(organization)).status_code == 403
    api_client.force_authenticate(manager)
    hidden = api_client.post(reverse("reviews-moderate", args=[review.id]), {"moderation_status": "HIDDEN", "reason": ""}, format="json", **headers(organization))
    assert hidden.status_code == 400
    approved = api_client.post(reverse("reviews-moderate", args=[review.id]), {"moderation_status": "APPROVED"}, format="json", **headers(organization))
    assert approved.status_code == 200
    api_client.force_authenticate(None)
    public = api_client.get(public_url, **headers(organization))
    assert public.data["review_count"] == 1 and public.data["reviews"][0]["comment"] == review.comment
    assert "appointment" not in public.data["reviews"][0] and "customer" not in public.data["reviews"][0]
    api_client.force_authenticate(physio_user)
    mine = api_client.get(reverse("reviews-practitioner-mine"), **headers(organization))
    assert mine.data["review_count"] == 1 and mine.data["average_rating"] == 5.0
    api_client.force_authenticate(owner)
    api_client.post(reverse("reviews-moderate", args=[review.id]), {"moderation_status": "HIDDEN", "reason": "Contains private information"}, format="json", **headers(organization))
    assert AppointmentRatingModerationEvent.objects.filter(rating=review).count() == 2
    api_client.force_authenticate(None)
    assert api_client.get(public_url, **headers(organization)).data["review_count"] == 0


def test_cross_tenant_review_and_review_visibility_are_denied(api_client):
    values = setup_domain("review-tenant-a")
    _, review = submit_review(api_client, values)
    foreign = setup_domain("review-tenant-b")
    foreign_org, _, _, foreign_manager, foreign_physio, _, foreign_customer, *_ = foreign
    api_client.force_authenticate(foreign_customer)
    assert api_client.post(reverse("schedule-customer-rating", args=[review.appointment_id]), {"stars": 5, "comment": "Not mine"}, format="json", **headers(foreign_org)).status_code == 404
    api_client.force_authenticate(foreign_manager)
    assert api_client.post(reverse("reviews-moderate", args=[review.id]), {"moderation_status": "APPROVED"}, format="json", **headers(foreign_org)).status_code == 404
    api_client.force_authenticate(foreign_physio)
    assert api_client.get(reverse("reviews-practitioner-mine"), **headers(foreign_org)).data["review_count"] == 0
