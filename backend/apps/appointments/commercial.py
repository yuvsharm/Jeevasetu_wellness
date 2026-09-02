from dataclasses import asdict, dataclass
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone

from apps.appointments.models import CommercialOffer, TherapyOption, TherapyPackage

MONEY = Decimal("0.01")


@dataclass
class CommercialQuote:
    therapy_ids: list[str]
    therapy_names: list[str]
    therapy_prices: dict[str, str]
    package_id: str | None
    package_name: str
    offer_id: str | None
    offer_title: str
    session_count: int
    regular_amount: str
    discount_amount: str
    final_amount: str
    free_benefits: list[dict]
    duration_minutes: int

    def snapshot(self):
        return asdict(self)


def _money(value):
    return Decimal(value).quantize(MONEY, rounding=ROUND_HALF_UP)


def _therapy_duration(therapy):
    return therapy.default_duration_minutes or 45


def calculate_quote(*, organization, therapy_ids, package_id=None, offer_id=None, family_member=None, at=None):
    at = at or timezone.now()
    unique_ids = list(dict.fromkeys(str(value) for value in therapy_ids))
    therapies = list(
        TherapyOption.objects.filter(
            id__in=unique_ids,
            organization=organization,
            is_active=True,
            is_publicly_visible=True,
        )
    )
    if len(therapies) != len(unique_ids) or not therapies:
        raise ValidationError({"therapies": "Select active therapies from this organization."})
    by_id = {str(item.id): item for item in therapies}
    therapies = [by_id[value] for value in unique_ids]
    package = None
    offer = None
    session_count = 1
    regular = sum((_money(item.base_price) for item in therapies), Decimal("0.00"))
    final = regular
    free_benefits = []

    if package_id and offer_id:
        raise ValidationError({"offer": "Only one package or promotional offer may be applied."})
    if not package_id and not offer_id:
        eligible_quotes = []
        candidates = CommercialOffer.objects.filter(
            organization=organization,
            is_active=True,
            is_publicly_visible=True,
        ).filter(
            Q(valid_from__isnull=True) | Q(valid_from__lte=at),
            Q(valid_until__isnull=True) | Q(valid_until__gt=at),
        ).values_list("id", flat=True)
        for candidate_id in candidates:
            try:
                eligible_quotes.append(calculate_quote(
                    organization=organization,
                    therapy_ids=unique_ids,
                    offer_id=candidate_id,
                    family_member=family_member,
                    at=at,
                ))
            except ValidationError:
                continue
        if eligible_quotes:
            return min(
                eligible_quotes,
                key=lambda quote: (Decimal(quote.final_amount), -len(quote.free_benefits)),
            )
    if package_id:
        package = TherapyPackage.objects.filter(id=package_id, organization=organization).select_related("therapy").first()
        if not package or not package.is_publicly_visible or not package.is_current(at) or str(package.therapy_id) not in unique_ids:
            raise ValidationError({"package": "This package is not eligible for the selected therapy."})
        if len(unique_ids) != 1:
            raise ValidationError({"package": "A single-therapy package cannot be combined with other therapies."})
        session_count = package.session_count
        regular = _money(package.therapy.base_price * package.session_count)
        final = _money(package.selling_price)
    if offer_id:
        offer = CommercialOffer.objects.filter(id=offer_id, organization=organization).prefetch_related("eligible_therapies").select_related("free_therapy", "qualifying_package").first()
        if not offer or not offer.is_publicly_visible or not offer.is_current(at):
            raise ValidationError({"offer": "This offer is not currently available."})
        eligible_ids = {str(value) for value in offer.eligible_therapies.values_list("id", flat=True)}
        selected_eligible = [item for item in therapies if str(item.id) in eligible_ids]
        count = len(selected_eligible)
        if count < offer.minimum_therapy_count or (offer.maximum_therapy_count and count > offer.maximum_therapy_count):
            raise ValidationError({"offer": "The selected therapies do not meet this offer's therapy-count rules."})
        if offer.family_required or offer.offer_type in (CommercialOffer.OfferType.FAMILY, CommercialOffer.OfferType.FAMILY_FREE):
            if not family_member:
                raise ValidationError({"offer": "This offer requires an owned family-member booking."})
            owned_count = family_member.customer.family_members.filter(is_active=True).count()
            if owned_count < offer.minimum_family_members:
                raise ValidationError({"offer": f"Register at least {offer.minimum_family_members} family members to use this offer."})
        if offer.offer_type == CommercialOffer.OfferType.THERAPY_DISCOUNT:
            discounts = {str(rule["therapy_id"]): rule for rule in offer.rule_config.get("therapy_discounts", [])}
            final = Decimal("0.00")
            for item in therapies:
                price = _money(item.base_price)
                rule = discounts.get(str(item.id))
                if not rule:
                    final += price
                elif rule["discount_type"] == "PERCENTAGE":
                    final += _money(price * (Decimal("100") - Decimal(str(rule["discount"]))) / Decimal("100"))
                else:
                    final += max(Decimal("0.00"), _money(price - Decimal(str(rule["discount"]))))
        if offer.offer_type == CommercialOffer.OfferType.FIXED_BUNDLE and {str(item.id) for item in therapies} != eligible_ids:
            raise ValidationError({"offer": "Select every therapy in this fixed bundle."})
        if offer.offer_type in (CommercialOffer.OfferType.PERCENTAGE, CommercialOffer.OfferType.FAMILY):
            if offer.offer_type == CommercialOffer.OfferType.FAMILY and offer.rule_config.get("discount_type") == "FIXED":
                final = max(Decimal("0.00"), _money(regular - offer.discount_value))
            else:
                final = _money(regular * (Decimal("100") - offer.discount_value) / Decimal("100"))
        elif offer.offer_type == CommercialOffer.OfferType.FIXED_DISCOUNT:
            final = max(Decimal("0.00"), _money(regular - offer.discount_value))
        elif offer.offer_type == CommercialOffer.OfferType.FIXED_BUNDLE:
            final = _money(offer.fixed_price)
        elif offer.offer_type == CommercialOffer.OfferType.FREE_THERAPY:
            free_benefits.append({"therapy_id": str(offer.free_therapy_id), "therapy_name": offer.free_therapy.name, "quantity": offer.free_quantity, "unit_price": "0.00", "duration_minutes": _therapy_duration(offer.free_therapy)})
        elif offer.offer_type == CommercialOffer.OfferType.FAMILY_FREE:
            free_benefits.append({"therapy_id": str(offer.free_therapy_id), "therapy_name": offer.free_therapy.name, "quantity": 1, "unit_price": "0.00", "duration_minutes": _therapy_duration(offer.free_therapy)})

    discount = max(Decimal("0.00"), _money(regular - final))
    duration_minutes = sum(_therapy_duration(item) for item in therapies)
    if offer and free_benefits:
        duration_minutes += sum(
            _therapy_duration(offer.free_therapy) * item["quantity"]
            for item in free_benefits
        )
    return CommercialQuote(
        therapy_ids=[str(item.id) for item in therapies],
        therapy_names=[item.name for item in therapies],
        therapy_prices={str(item.id): str(_money(item.base_price)) for item in therapies},
        package_id=str(package.id) if package else None,
        package_name=package.name if package else "",
        offer_id=str(offer.id) if offer else None,
        offer_title=offer.title if offer else "",
        session_count=session_count,
        regular_amount=str(_money(regular)),
        discount_amount=str(discount),
        final_amount=str(_money(final)),
        free_benefits=free_benefits,
        duration_minutes=duration_minutes,
    )
