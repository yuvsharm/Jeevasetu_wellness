import logging

from django.db import transaction

from apps.accounts.models import Notification, Role, RoleAssignment


logger = logging.getLogger(__name__)


def _safe_target_url(value):
    return value if value.startswith("/") and not value.startswith("//") else "/dashboard"


def _persist_notification(payload):
    try:
        Notification.objects.get_or_create(
            organization_id=payload["organization_id"],
            recipient_id=payload["recipient_id"],
            recipient_role=payload["recipient_role"],
            dedupe_key=payload["dedupe_key"],
            defaults={key: value for key, value in payload.items() if key not in {
                "organization_id", "recipient_id", "recipient_role", "dedupe_key"
            }},
        )
    except Exception:
        logger.exception("Could not persist in-app notification %s", payload["dedupe_key"])


def notify_user(*, organization, recipient, recipient_role, notification_type, category,
                title, message, related_object_type, related_object_id, target_url,
                action_required=False, dedupe_key=None):
    if recipient is None:
        return
    recipient_id = getattr(recipient, "id", recipient)
    object_id = str(related_object_id)
    payload = {
        "organization_id": organization.id,
        "recipient_id": recipient_id,
        "recipient_role": recipient_role,
        "notification_type": notification_type,
        "category": category,
        "title": title[:160],
        "message": message[:500],
        "related_object_type": related_object_type[:64],
        "related_object_id": object_id[:64],
        "target_url": _safe_target_url(target_url)[:500],
        "action_required": action_required,
        "dedupe_key": (dedupe_key or f"{notification_type}:{object_id}")[:255],
    }
    transaction.on_commit(lambda: _persist_notification(payload))


def notify_owners(*, organization, **notification):
    owner_ids = RoleAssignment.objects.filter(
        organization=organization,
        role=Role.OWNER,
        is_active=True,
        organization_membership__is_active=True,
        user__is_active=True,
        user__is_enabled=True,
    ).values_list("user_id", flat=True).distinct()
    for owner_id in owner_ids:
        notify_user(
            organization=organization,
            recipient=owner_id,
            recipient_role=Role.OWNER,
            **notification,
        )
