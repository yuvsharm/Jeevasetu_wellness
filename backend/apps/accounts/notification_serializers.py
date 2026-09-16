from rest_framework import serializers

from apps.accounts.models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    is_read = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = (
            "id", "notification_type", "category", "title", "message", "target_url",
            "action_required", "is_read", "read_at", "created_at",
        )

    def get_is_read(self, value):
        return value.read_at is not None
