from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from apps.accounts.models import (
    AuthenticationAuditEvent,
    PasswordResetRequest,
    RoleAssignment,
    User,
)


@admin.register(User)
class IdentityUserAdmin(UserAdmin):
    list_display = ("email", "mobile_number", "is_active", "is_enabled", "is_staff")
    list_filter = ("is_active", "is_enabled", "is_staff", "is_superuser")
    fieldsets = UserAdmin.fieldsets + (
        ("Identity", {"fields": ("mobile_number", "is_enabled", "profile_image")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Identity", {"fields": ("email", "mobile_number", "is_enabled")}),
    )


@admin.register(RoleAssignment)
class RoleAssignmentAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "organization", "clinic", "is_active")
    list_filter = ("role", "is_active")
    search_fields = ("user__email", "user__mobile_number")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(PasswordResetRequest)
class PasswordResetRequestAdmin(admin.ModelAdmin):
    list_display = ("user", "created_at", "expires_at", "used_at")
    list_filter = ("created_at", "used_at")
    readonly_fields = ("id", "user", "token_digest", "created_at", "expires_at", "used_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(AuthenticationAuditEvent)
class AuthenticationAuditEventAdmin(admin.ModelAdmin):
    list_display = ("event", "outcome", "user", "ip_address", "created_at")
    list_filter = ("event", "outcome", "created_at")
    search_fields = ("user__email", "user__mobile_number", "identifier_hash")
    readonly_fields = (
        "id",
        "event",
        "outcome",
        "user",
        "identifier_hash",
        "ip_address",
        "user_agent",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
