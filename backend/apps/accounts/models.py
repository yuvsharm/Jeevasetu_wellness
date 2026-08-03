import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Minimal identity model reserved before the first production migration."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
