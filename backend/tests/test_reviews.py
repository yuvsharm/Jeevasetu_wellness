import pytest
from django.db import IntegrityError, transaction
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
    appointment.assignment_status = Appointment.AssignmentStatus.ACCEPTED
    appointment.completed_at = timezone.now()
    appointment.save(update_fields=("status", "assignment_status", "completed_at"))
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
    assert api_client.post(reverse("reviews-moderate", args=[review.id]), {"moderation_status": "HIDDEN", "reason": "Operations request"}, format="json", **headers(organization)).status_code == 403
    assert api_client.post(reverse("reviews-moderate", args=[review.id]), {"moderation_status": "APPROVED"}, format="json", **headers(organization)).status_code == 403
    api_client.force_authenticate(owner)
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


def test_review_requires_accepted_delivered_assignment_and_derives_therapist(api_client):
    values = setup_domain("review-delivered-therapist")
    organization, _, _, _, _, delivered_therapist, customer, *_ = values
    appointment = create_scheduled(api_client, values)
    appointment.status = Appointment.Status.COMPLETED
    appointment.completed_at = timezone.now()
    appointment.save(update_fields=("status", "completed_at"))
    api_client.force_authenticate(customer)
    url = reverse("schedule-customer-rating", args=[appointment.id])

    not_accepted = api_client.post(
        url,
        {"stars": 5, "comment": "Great care", "physiotherapist": "not-trusted"},
        format="json",
        **headers(organization),
    )
    assert not_accepted.status_code == 404

    appointment.assignment_status = Appointment.AssignmentStatus.ACCEPTED
    appointment.save(update_fields=("assignment_status",))
    submitted = api_client.post(
        url,
        {"stars": 5, "comment": "Great care", "physiotherapist": "not-trusted"},
        format="json",
        **headers(organization),
    )
    review = AppointmentRating.objects.get(appointment=appointment)
    assert submitted.status_code == 201
    assert review.physiotherapist == delivered_therapist
    assert review.moderation_status == AppointmentRating.ModerationStatus.PENDING


def test_submitted_review_is_immutable_through_api_for_every_role(api_client):
    values = setup_domain("review-immutable")
    organization, _, owner, manager, physio_user, _, customer, *_ = values
    appointment, review = submit_review(api_client, values)
    rating_url = reverse("schedule-customer-rating", args=[appointment.id])
    moderation_url = reverse("reviews-moderate", args=[review.id])

    api_client.force_authenticate(customer)
    duplicate = api_client.post(
        rating_url,
        {"stars": 1, "comment": "Replacement"},
        format="json",
        **headers(organization),
    )
    assert duplicate.status_code == 400
    assert "Feedback has already been submitted" in str(duplicate.data)
    assert api_client.patch(rating_url, {"stars": 1}, format="json", **headers(organization)).status_code == 405
    assert api_client.put(rating_url, {"comment": "Changed"}, format="json", **headers(organization)).status_code == 405
    assert api_client.delete(rating_url, **headers(organization)).status_code == 405

    for actor in (physio_user, manager):
        api_client.force_authenticate(actor)
        assert api_client.patch(rating_url, {"stars": 1}, format="json", **headers(organization)).status_code in (403, 405)
        assert api_client.delete(rating_url, **headers(organization)).status_code in (403, 405)
        assert api_client.post(
            moderation_url,
            {"moderation_status": "APPROVED", "stars": 1, "comment": "Changed"},
            format="json",
            **headers(organization),
        ).status_code == 403

    review.refresh_from_db()
    assert review.stars == 5
    assert review.comment == "Excellent and professional service"
    assert review.moderation_status == AppointmentRating.ModerationStatus.PENDING

    api_client.force_authenticate(owner)
    moderated = api_client.post(
        moderation_url,
        {"moderation_status": "APPROVED", "stars": 1, "comment": "Changed"},
        format="json",
        **headers(organization),
    )
    review.refresh_from_db()
    assert moderated.status_code == 200
    assert review.stars == 5
    assert review.comment == "Excellent and professional service"
    assert review.moderation_status == AppointmentRating.ModerationStatus.APPROVED


def test_database_rejects_a_second_review_for_the_same_appointment(api_client):
    values = setup_domain("review-database-unique")
    organization, _, _, _, _, therapist, customer, *_ = values
    appointment, _ = submit_review(api_client, values)

    with pytest.raises(IntegrityError), transaction.atomic():
        AppointmentRating.objects.create(
            appointment=appointment,
            organization=organization,
            customer=customer,
            physiotherapist=therapist,
            stars=4,
            comment="Duplicate concurrent insert",
        )

    assert AppointmentRating.objects.filter(appointment=appointment).count() == 1


def test_cross_tenant_review_and_review_visibility_are_denied(api_client):
    values = setup_domain("review-tenant-a")
    _, review = submit_review(api_client, values)
    foreign = setup_domain("review-tenant-b")
    foreign_org, _, foreign_owner, foreign_manager, foreign_physio, _, foreign_customer, *_ = foreign
    api_client.force_authenticate(foreign_customer)
    assert api_client.post(reverse("schedule-customer-rating", args=[review.appointment_id]), {"stars": 5, "comment": "Not mine"}, format="json", **headers(foreign_org)).status_code == 404
    api_client.force_authenticate(foreign_manager)
    assert api_client.post(reverse("reviews-moderate", args=[review.id]), {"moderation_status": "APPROVED"}, format="json", **headers(foreign_org)).status_code == 403
    api_client.force_authenticate(foreign_owner)
    assert api_client.post(reverse("reviews-moderate", args=[review.id]), {"moderation_status": "APPROVED"}, format="json", **headers(foreign_org)).status_code == 404
    api_client.force_authenticate(foreign_physio)
    assert api_client.get(reverse("reviews-practitioner-mine"), **headers(foreign_org)).data["review_count"] == 0


def test_public_practitioner_rating_only_completed_approved_services(api_client):
    from apps.practitioners.models import PractitionerProfile
    values=setup_domain("public-card-rating")
    organization,clinic,_,_,user,staff,*_=values
    appointment,rating=submit_review(api_client,values,stars=4)
    PractitionerProfile.objects.create(user=user,organization=organization,clinic=clinic,staff_profile=staff,
        is_approved=True,is_publicly_visible=True,is_open_to_work=True,category="PHYSIOTHERAPIST",approved_at=timezone.now())
    api_client.force_authenticate(None)
    url=reverse("practitioner-public-list")
    assert api_client.get(url,**headers(organization)).data[0]["review_count"]==0
    rating.moderation_status="APPROVED";rating.save()
    result=api_client.get(url,**headers(organization)).data[0]
    assert result["review_count"]==1 and result["average_rating"]==4.0
    appointment.status="CANCELLED";appointment.save(update_fields=["status"])
    assert api_client.get(url,**headers(organization)).data[0]["review_count"]==0
