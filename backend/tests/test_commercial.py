from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.appointments.commercial import calculate_quote
from apps.appointments.models import AppointmentRequest, CommercialOffer, TherapyOption, TherapyPackage
from apps.patients.models import CustomerFamilyMember
from tests.test_appointments import issue_and_verify, payload, setup_identity, tenant
from tests.test_scheduling import headers, setup_domain

pytestmark = pytest.mark.django_db


def add_therapy(organization, slug, price):
    return TherapyOption.objects.create(organization=organization, name=slug.title(), slug=slug, base_price=price, default_duration_minutes=45)


def test_package_totals_and_price_snapshot_are_derived_and_stable():
    organization, *_, therapy = setup_domain("commercial-package")
    therapy.base_price = Decimal("1200")
    therapy.save(update_fields=("base_price",))
    package = TherapyPackage.objects.create(organization=organization, name="7 Session Plan", therapy=therapy, session_count=7, selling_price=7000)
    quote = calculate_quote(organization=organization, therapy_ids=[therapy.id], package_id=package.id)
    assert quote.regular_amount == "8400.00" and quote.discount_amount == "1400.00"
    snapshot = quote.snapshot()
    therapy.base_price = Decimal("1500")
    therapy.save(update_fields=("base_price",))
    package.selling_price = Decimal("7600")
    package.save(update_fields=("selling_price",))
    assert snapshot["regular_amount"] == "8400.00" and snapshot["final_amount"] == "7000.00"


def test_percentage_fixed_bundle_and_stacking_rules():
    organization, *_, first = setup_domain("commercial-combos")
    first.base_price = 1000
    first.save(update_fields=("base_price",))
    second = add_therapy(organization, "potli", 1400)
    percentage = CommercialOffer.objects.create(organization=organization, title="Choose two", offer_type=CommercialOffer.OfferType.PERCENTAGE, minimum_therapy_count=2, maximum_therapy_count=2, discount_value=10)
    percentage.eligible_therapies.set([first, second])
    quote = calculate_quote(organization=organization, therapy_ids=[first.id, second.id], offer_id=percentage.id)
    assert quote.final_amount == "2160.00" and quote.duration_minutes == 90
    bundle = CommercialOffer.objects.create(organization=organization, title="Pain Relief", offer_type=CommercialOffer.OfferType.FIXED_BUNDLE, minimum_therapy_count=2, fixed_price=2050)
    bundle.eligible_therapies.set([first, second])
    assert calculate_quote(organization=organization, therapy_ids=[first.id, second.id], offer_id=bundle.id).discount_amount == "350.00"
    package = TherapyPackage.objects.create(organization=organization, name="Plan", therapy=first, session_count=2, selling_price=1700)
    with pytest.raises(ValidationError):
        calculate_quote(organization=organization, therapy_ids=[first.id], package_id=package.id, offer_id=percentage.id)


def test_family_and_free_addon_eligibility_and_duration():
    values = setup_domain("commercial-family")
    organization, _, _, _, _, _, customer, _, _, first = values
    first.base_price = 1000
    first.save(update_fields=("base_price",))
    family = CustomerFamilyMember.objects.create(organization=organization, customer=customer, full_name="Meera", age=50, gender="FEMALE", relationship="Mother")
    family_offer = CommercialOffer.objects.create(organization=organization, title="Family care", offer_type=CommercialOffer.OfferType.FAMILY, family_required=True, discount_value=20)
    family_offer.eligible_therapies.set([first])
    with pytest.raises(ValidationError):
        calculate_quote(organization=organization, therapy_ids=[first.id], offer_id=family_offer.id)
    assert calculate_quote(organization=organization, therapy_ids=[first.id], offer_id=family_offer.id, family_member=family).final_amount == "800.00"
    free = add_therapy(organization, "plain-massage", 500)
    addon = CommercialOffer.objects.create(organization=organization, title="Free massage", offer_type=CommercialOffer.OfferType.FREE_THERAPY, discount_value=0, free_therapy=free, free_quantity=1)
    addon.eligible_therapies.set([first])
    quote = calculate_quote(organization=organization, therapy_ids=[first.id], offer_id=addon.id)
    assert quote.final_amount == "1000.00" and quote.duration_minutes == 90 and quote.free_benefits[0]["therapy_id"] == str(free.id)


def test_expired_future_private_and_cross_tenant_catalog_security(api_client):
    values = setup_domain("commercial-security")
    organization, _, owner, manager, physio, _, customer, *_, therapy = values
    therapy.base_price = 500
    therapy.save(update_fields=("base_price",))
    future = CommercialOffer.objects.create(organization=organization, title="Future", offer_type=CommercialOffer.OfferType.PERCENTAGE, discount_value=10, valid_from=timezone.now() + timedelta(days=1))
    future.eligible_therapies.set([therapy])
    expired = CommercialOffer.objects.create(organization=organization, title="Expired", offer_type=CommercialOffer.OfferType.PERCENTAGE, discount_value=10, valid_until=timezone.now() - timedelta(days=1))
    expired.eligible_therapies.set([therapy])
    public = api_client.get(reverse("commercial-public"), **headers(organization))
    assert public.status_code == 200 and public.data["offers"] == []
    payload = {"name": "New Therapy", "slug": "new-therapy", "base_price": "900.00", "default_duration_minutes": 45}
    for actor, expected in ((customer, 403), (physio, 403), (manager, 201)):
        api_client.force_authenticate(actor)
        assert api_client.post(reverse("commercial-therapy-list"), payload, format="json", **headers(organization)).status_code == expected
    foreign = setup_domain("commercial-foreign")
    api_client.force_authenticate(foreign[3])
    assert api_client.patch(reverse("commercial-therapy-detail", args=[therapy.id]), {"base_price": "1.00"}, format="json", **headers(foreign[0])).status_code == 404
    api_client.force_authenticate(owner)
    assert api_client.patch(reverse("commercial-therapy-detail", args=[therapy.id]), {"base_price": "-1.00"}, format="json", **headers(organization)).status_code == 400


def test_secure_booking_recalculates_offer_and_preserves_snapshot(api_client):
    organization, _, first = setup_identity("CUSTOMER")
    first.base_price = 1000
    first.save(update_fields=("base_price",))
    free = add_therapy(organization, "free-addon", 400)
    offer = CommercialOffer.objects.create(organization=organization, title="Free add-on", offer_type=CommercialOffer.OfferType.FREE_THERAPY, free_therapy=free, free_quantity=1)
    offer.eligible_therapies.set([first])
    _, token = issue_and_verify(api_client, organization)
    data = payload(first)
    data.update(booking_verification_token=token, selected_offer=str(offer.id), regular_amount="1.00", final_amount="1.00")
    created = api_client.post(reverse("quick-appointment-create"), data, format="json", **tenant(organization.slug))
    assert created.status_code == 201
    value = AppointmentRequest.objects.get(pk=created.data["id"])
    assert value.final_amount == Decimal("1000.00")
    assert value.commercial_snapshot["duration_minutes"] == 90
    assert free in value.requested_therapies.all()
    first.base_price = 2000
    first.save(update_fields=("base_price",))
    value.refresh_from_db()
    assert value.commercial_snapshot["regular_amount"] == "1000.00"
