from datetime import time, timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.appointments.commercial import calculate_quote
from apps.appointments.models import AppointmentRequest, CommercialOffer, TherapyOption, TherapyPackage
from apps.patients.models import CustomerFamilyMember
from tests.test_appointments import authenticated_payload, setup_identity, tenant
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
    with pytest.raises(ValidationError):
        calculate_quote(organization=organization, therapy_ids=[therapy.id], offer_id=expired.id)
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
    organization, customer, first = setup_identity("CUSTOMER")
    first.base_price = 1000
    first.save(update_fields=("base_price",))
    free = add_therapy(organization, "free-addon", 400)
    offer = CommercialOffer.objects.create(organization=organization, title="Free add-on", offer_type=CommercialOffer.OfferType.FREE_THERAPY, free_therapy=free, free_quantity=1)
    offer.eligible_therapies.set([first])
    api_client.force_authenticate(customer)
    data = authenticated_payload(first)
    data.update({"regular_amount": "1.00", "discount_amount": "999999.00", "final_amount": "0.01"})
    created = api_client.post(reverse("quick-appointment-create"), data, format="json", **tenant(organization.slug))
    assert created.status_code == 201
    value = AppointmentRequest.objects.get(pk=created.data["id"])
    assert value.selected_offer_id == offer.id
    assert value.final_amount == Decimal("1000.00")
    assert value.commercial_snapshot["duration_minutes"] == 90
    assert free in value.requested_therapies.all()
    first.base_price = 2000
    first.save(update_fields=("base_price",))
    value.refresh_from_db()
    assert value.commercial_snapshot["regular_amount"] == "1000.00"


def test_guided_per_therapy_discounts_are_authoritative():
    organization, *_, first = setup_domain("commercial-guided-therapy")
    first.base_price = 1000
    first.save(update_fields=("base_price",))
    second = add_therapy(organization, "guided-potli", 1400)
    offer = CommercialOffer.objects.create(
        organization=organization,
        title="Different therapy savings",
        offer_type=CommercialOffer.OfferType.THERAPY_DISCOUNT,
        rule_config={"therapy_discounts": [
            {"therapy_id": str(first.id), "discount_type": "PERCENTAGE", "discount": 10},
            {"therapy_id": str(second.id), "discount_type": "FIXED", "discount": 500},
        ]},
    )
    offer.eligible_therapies.set([first, second])
    quote = calculate_quote(organization=organization, therapy_ids=[first.id, second.id], offer_id=offer.id)
    assert quote.regular_amount == "2400.00"
    assert quote.final_amount == "1800.00"


def test_guided_family_fixed_and_free_offers_require_owned_family_threshold():
    organization, _, _, _, _, _, customer, _, _, first = setup_domain("commercial-guided-family")
    first.base_price = 1000
    first.save(update_fields=("base_price",))
    first_member = CustomerFamilyMember.objects.create(organization=organization, customer=customer, full_name="Meera", age=50, gender="FEMALE", relationship="Mother")
    fixed = CommercialOffer.objects.create(organization=organization, title="Family fixed saving", offer_type=CommercialOffer.OfferType.FAMILY, family_required=True, minimum_family_members=2, discount_value=250, rule_config={"discount_type": "FIXED"})
    fixed.eligible_therapies.set([first])
    with pytest.raises(ValidationError):
        calculate_quote(organization=organization, therapy_ids=[first.id], offer_id=fixed.id, family_member=first_member)
    CustomerFamilyMember.objects.create(organization=organization, customer=customer, full_name="Ravi", age=52, gender="MALE", relationship="Father")
    assert calculate_quote(organization=organization, therapy_ids=[first.id], offer_id=fixed.id, family_member=first_member).final_amount == "750.00"
    free = add_therapy(organization, "family-free", 500)
    free_offer = CommercialOffer.objects.create(organization=organization, title="Family free care", offer_type=CommercialOffer.OfferType.FAMILY_FREE, family_required=True, minimum_family_members=2, free_therapy=free)
    free_offer.eligible_therapies.set([first])
    quote = calculate_quote(organization=organization, therapy_ids=[first.id], offer_id=free_offer.id, family_member=first_member)
    assert quote.final_amount == "1000.00" and quote.free_benefits[0]["therapy_id"] == str(free.id)


def test_guided_offer_api_owner_manager_permissions_validation_and_tenant_isolation(api_client):
    organization, _, owner, manager, _, _, customer, *_, therapy = setup_domain("commercial-guided-api")
    payload = {
        "title": "September Therapy Offer",
        "offer_type": "THERAPY_DISCOUNT",
        "eligible_therapies": [str(therapy.id)],
        "discount_value": "0",
        "rule_config": {"therapy_discounts": [{"therapy_id": str(therapy.id), "discount_type": "PERCENTAGE", "discount": 10}]},
        "valid_from": (timezone.now() + timedelta(hours=1)).isoformat(),
        "valid_until": (timezone.now() + timedelta(days=2)).isoformat(),
        "is_active": True,
        "is_publicly_visible": True,
    }
    api_client.force_authenticate(customer)
    assert api_client.post(reverse("commercial-offer-list"), payload, format="json", **headers(organization)).status_code == 403
    api_client.force_authenticate(manager)
    created = api_client.post(reverse("commercial-offer-list"), payload, format="json", **headers(organization))
    assert created.status_code == 201
    api_client.force_authenticate(owner)
    invalid = api_client.post(reverse("commercial-offer-list"), {**payload, "title": "Expired", "valid_until": (timezone.now() - timedelta(minutes=1)).isoformat()}, format="json", **headers(organization))
    assert invalid.status_code == 400 and "valid_until" in invalid.data
    foreign = setup_domain("commercial-guided-api-foreign")
    api_client.force_authenticate(foreign[3])
    assert api_client.patch(reverse("commercial-offer-detail", args=[created.data["id"]]), {"is_active": False}, format="json", **headers(foreign[0])).status_code == 404


def test_owner_contract_creates_current_public_offer_and_booking_applies_only_when_eligible(api_client):
    organization, _, owner, *_values, eligible = setup_domain("commercial-owner-e2e")
    eligible.base_price = Decimal("1000")
    eligible.save(update_fields=("base_price",))
    other = add_therapy(organization, "unrelated-care", 700)
    now = timezone.now()
    payload = {
        "title": "Active Wellness Test Offer",
        "promotional_text": "Save on selected care",
        "offer_type": "PERCENTAGE",
        "eligible_therapies": [str(eligible.id)],
        "minimum_therapy_count": 1,
        "maximum_therapy_count": None,
        "discount_value": "10",
        "fixed_price": None,
        "free_therapy": None,
        "free_quantity": 1,
        "family_required": False,
        "minimum_family_members": 1,
        "rule_config": {"discount_type": "PERCENTAGE"},
        "valid_from": (now - timedelta(minutes=1)).isoformat(),
        "valid_until": (now + timedelta(days=1)).isoformat(),
        "is_active": True,
        "is_publicly_visible": True,
        "display_order": 0,
    }
    api_client.force_authenticate(owner)
    created = api_client.post(reverse("commercial-offer-list"), payload, format="json", **headers(organization))
    assert created.status_code == 201
    saved = CommercialOffer.objects.get(pk=created.data["id"])
    assert saved.title == payload["title"] and saved.is_current(now) and saved.is_publicly_visible

    public = api_client.get(reverse("commercial-public"), **headers(organization))
    assert created.data["id"] in {str(item["id"]) for item in public.data["offers"]}
    eligible_quote = calculate_quote(organization=organization, therapy_ids=[eligible.id], at=now)
    assert eligible_quote.offer_id == str(saved.id) and eligible_quote.final_amount == "900.00"
    unrelated_quote = calculate_quote(organization=organization, therapy_ids=[other.id], at=now)
    assert unrelated_quote.offer_id is None and unrelated_quote.final_amount == "700.00"
    with pytest.raises(ValidationError):
        calculate_quote(organization=organization, therapy_ids=[other.id], offer_id=saved.id, at=now)

    deactivated = api_client.patch(reverse("commercial-offer-detail", args=[saved.id]), {"is_active": False}, format="json", **headers(organization))
    assert deactivated.status_code == 200
    public = api_client.get(reverse("commercial-public"), **headers(organization))
    assert created.data["id"] not in {str(item["id"]) for item in public.data["offers"]}
    assert calculate_quote(organization=organization, therapy_ids=[eligible.id], at=now).final_amount == "1000.00"
    with pytest.raises(ValidationError):
        calculate_quote(organization=organization, therapy_ids=[eligible.id], offer_id=saved.id, at=now)


def test_therapy_management_add_edit_safe_delete_deactivate_manager_scope(api_client):
    organization, _, owner, manager, *_, used = setup_domain("therapy-management")
    payload = {
        "name": "Unused Local Therapy",
        "slug": "unused-local-therapy",
        "short_description": "Temporary catalogue entry",
        "detailed_description": "Created only inside this isolated test.",
        "benefits": ["Test benefit"],
        "default_duration_minutes": 45,
        "base_price": "900.00",
        "is_active": True,
        "is_publicly_visible": True,
        "display_order": 20,
    }
    api_client.force_authenticate(manager)
    created = api_client.post(reverse("commercial-therapy-list"), payload, format="json", **headers(organization))
    assert created.status_code == 201 and created.data["can_delete"] is True
    therapy_id = created.data["id"]

    api_client.force_authenticate(owner)
    updated = api_client.patch(reverse("commercial-therapy-detail", args=[therapy_id]), {"base_price": "950.00"}, format="json", **headers(organization))
    assert updated.status_code == 200 and updated.data["base_price"] == "950.00"
    assert TherapyOption.objects.filter(pk=therapy_id).count() == 1

    api_client.force_authenticate(manager)
    deleted = api_client.delete(reverse("commercial-therapy-detail", args=[therapy_id]), **headers(organization))
    assert deleted.status_code == 204 and not TherapyOption.objects.filter(pk=therapy_id).exists()

    TherapyPackage.objects.create(organization=organization, name="Protected Plan", therapy=used, session_count=2, selling_price=100)
    listing = api_client.get(reverse("commercial-therapy-list"), **headers(organization))
    protected = next(item for item in listing.data if str(item["id"]) == str(used.id))
    assert protected["can_delete"] is False and protected["protected_references"]["packages"] == 1
    blocked = api_client.delete(reverse("commercial-therapy-detail", args=[used.id]), **headers(organization))
    assert blocked.status_code == 400 and "cannot be deleted" in blocked.data["detail"]
    deactivated = api_client.patch(reverse("commercial-therapy-detail", args=[used.id]), {"is_active": False}, format="json", **headers(organization))
    assert deactivated.status_code == 200 and deactivated.data["is_active"] is False

    foreign = setup_domain("therapy-management-foreign")
    api_client.force_authenticate(foreign[3])
    assert api_client.patch(reverse("commercial-therapy-detail", args=[used.id]), {"is_active": True}, format="json", **headers(foreign[0])).status_code == 404


def test_offer_uses_service_date_and_safe_delete_preserves_used_offer(api_client):
    organization, _, owner, _, _, _, customer, _, _, therapy = setup_domain("offer-service-date")
    therapy.base_price = Decimal("1000")
    therapy.save(update_fields=("base_price",))
    now = timezone.now()
    offer = CommercialOffer.objects.create(
        organization=organization,
        title="Service Week Offer",
        offer_type=CommercialOffer.OfferType.PERCENTAGE,
        discount_value=10,
        valid_from=now + timedelta(days=2),
        valid_until=now + timedelta(days=5),
    )
    offer.eligible_therapies.set([therapy])
    inside = now + timedelta(days=3)
    outside = now + timedelta(days=7)
    assert calculate_quote(organization=organization, therapy_ids=[therapy.id], at=inside).final_amount == "900.00"
    assert calculate_quote(organization=organization, therapy_ids=[therapy.id], at=outside).final_amount == "1000.00"
    quoted_inside = api_client.post(
        reverse("commercial-quote"),
        {"therapy_ids": [str(therapy.id)], "service_at": inside.isoformat()},
        format="json", **headers(organization),
    )
    quoted_outside = api_client.post(
        reverse("commercial-quote"),
        {"therapy_ids": [str(therapy.id)], "service_at": outside.isoformat()},
        format="json", **headers(organization),
    )
    assert quoted_inside.data["final_amount"] == "900.00"
    assert quoted_outside.data["final_amount"] == "1000.00"

    api_client.force_authenticate(owner)
    listing = api_client.get(reverse("commercial-offer-list"), **headers(organization))
    listed = next(item for item in listing.data if str(item["id"]) == str(offer.id))
    assert listed["can_delete"] is True

    AppointmentRequest.objects.create(
        organization=organization,
        creator=customer,
        therapy=therapy,
        selected_offer=offer,
        patient_name="Offer Customer",
        age=30,
        gender="OTHER",
        mobile_number="9876543210",
        session_preference="SINGLE",
        preferred_date=inside.date(),
        preferred_time=time(10),
        address="Meerut",
        city="Meerut",
        pin_code="250004",
        commercial_snapshot=calculate_quote(
            organization=organization, therapy_ids=[therapy.id], offer_id=offer.id, at=inside
        ).snapshot(),
    )
    blocked = api_client.delete(reverse("commercial-offer-detail", args=[offer.id]), **headers(organization))
    assert blocked.status_code == 400
    assert blocked.data["detail"] == "This offer has historical booking records and cannot be permanently deleted. Archive it instead."
    archived = api_client.patch(
        reverse("commercial-offer-detail", args=[offer.id]),
        {"is_active": False}, format="json", **headers(organization),
    )
    assert archived.status_code == 200

    expired = CommercialOffer.objects.create(
        organization=organization,
        title="Expired archived offer",
        offer_type=CommercialOffer.OfferType.PERCENTAGE,
        discount_value=10,
        valid_from=now - timedelta(days=2),
        valid_until=now - timedelta(days=1),
        is_active=False,
    )
    expired.eligible_therapies.set([therapy])
    rejected_reactivation = api_client.patch(
        reverse("commercial-offer-detail", args=[expired.id]),
        {"is_active": True}, format="json", **headers(organization),
    )
    assert rejected_reactivation.status_code == 400
    assert rejected_reactivation.data["valid_until"][0] == "Edit the offer end date to a future date before reactivating it."
    reactivated = api_client.patch(
        reverse("commercial-offer-detail", args=[expired.id]),
        {"is_active": True, "valid_until": (now + timedelta(days=1)).isoformat()},
        format="json", **headers(organization),
    )
    assert reactivated.status_code == 200 and reactivated.data["is_active"] is True

    unused = CommercialOffer.objects.create(
        organization=organization,
        title="Unused Local Offer",
        offer_type=CommercialOffer.OfferType.FIXED_DISCOUNT,
        discount_value=100,
    )
    unused.eligible_therapies.set([therapy])
    deleted = api_client.delete(reverse("commercial-offer-detail", args=[unused.id]), **headers(organization))
    assert deleted.status_code == 204 and not CommercialOffer.objects.filter(pk=unused.id).exists()
