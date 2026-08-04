import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from apps.accounts.models import PasswordResetRequest


def token_digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def blacklist_user_refresh_tokens(user):
    for outstanding in OutstandingToken.objects.filter(user=user):
        BlacklistedToken.objects.get_or_create(token=outstanding)


@transaction.atomic
def issue_password_reset(user):
    now = timezone.now()
    PasswordResetRequest.objects.filter(user=user, used_at__isnull=True).update(used_at=now)
    token = secrets.token_urlsafe(32)
    request = PasswordResetRequest.objects.create(
        user=user,
        token_digest=token_digest(token),
        expires_at=now + timedelta(seconds=settings.AUTH_PASSWORD_RESET_TIMEOUT_SECONDS),
    )
    return request, token


@transaction.atomic
def consume_password_reset(uid, token, password):
    now = timezone.now()
    reset = (
        PasswordResetRequest.objects.select_for_update()
        .select_related("user")
        .filter(user_id=uid, token_digest=token_digest(token))
        .first()
    )
    if reset is None or reset.used_at is not None or reset.expires_at <= now:
        return None
    if not reset.user.is_active or not reset.user.is_enabled:
        return None
    reset.user.set_password(password)
    reset.user.save(update_fields=("password",))
    reset.used_at = now
    reset.save(update_fields=("used_at",))
    blacklist_user_refresh_tokens(reset.user)
    return reset.user
