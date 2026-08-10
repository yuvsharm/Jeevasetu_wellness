import pytest
from django.urls import reverse

from apps.practitioners.models import PractitionerApplication
from tests.test_practitioners import application, headers

pytestmark = pytest.mark.django_db
pytest_plugins = ("tests.test_practitioners",)


def test_failed_submission_returns_exact_requirements_and_stays_draft(api_client, domain):
    organization, _, _, applicant, _, _ = domain
    api_client.force_authenticate(applicant)
    created = api_client.post(
        reverse("practitioner-my-applications"), {}, format="json", **headers(organization)
    )

    response = api_client.post(
        reverse("practitioner-submit", args=[created.data["id"]]),
        {},
        format="json",
        **headers(organization),
    )

    persisted = PractitionerApplication.objects.get(pk=created.data["id"])
    assert response.status_code == 400
    assert persisted.status == PractitionerApplication.Status.DRAFT
    assert persisted.submitted_at is None
    labels = {item["label"] for item in response.data["missing_requirements"]}
    assert {"Profile photo", "Mobile number", "Government identity proof"} <= labels


def test_default_owner_queue_excludes_draft_and_submission_is_idempotent(api_client, domain):
    organization, _, _, applicant, _, owner = domain
    value = application(domain)
    api_client.force_authenticate(owner)
    before = api_client.get(reverse("practitioner-applications"), **headers(organization))
    assert str(value.id) not in {str(item["id"]) for item in before.data}

    api_client.force_authenticate(applicant)
    url = reverse("practitioner-submit", args=[value.id])
    first = api_client.post(url, {}, format="json", **headers(organization))
    second = api_client.post(url, {}, format="json", **headers(organization))

    api_client.force_authenticate(owner)
    after = api_client.get(reverse("practitioner-applications"), **headers(organization))
    assert first.status_code == second.status_code == 200
    assert first.data["submitted_at"] == second.data["submitted_at"]
    assert [str(item["id"]) for item in after.data].count(str(value.id)) == 1
