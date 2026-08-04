import uuid

from django.contrib.auth.models import UserManager as DjangoUserManager

from apps.accounts.validators import normalize_email_address, normalize_mobile_number


class UserManager(DjangoUserManager):
    def _create_user(self, username, email, password, **extra_fields):
        email = normalize_email_address(email)
        mobile = extra_fields.get("mobile_number")
        if mobile:
            extra_fields["mobile_number"] = normalize_mobile_number(mobile)
        if not username:
            username = f"user-{uuid.uuid4()}"
        return super()._create_user(username, email, password, **extra_fields)
