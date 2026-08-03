from django.contrib import admin

from apps.tenancy.models import Clinic, ClinicMembership, Organization, OrganizationMembership


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("display_name", "slug", "is_active", "timezone", "created_at")
    list_filter = ("is_active", "timezone")
    search_fields = ("legal_name", "display_name", "slug")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(Clinic)
class ClinicAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "slug", "is_active", "timezone")
    list_filter = ("is_active", "timezone", "organization")
    search_fields = ("name", "slug", "organization__display_name")
    readonly_fields = ("id", "created_at", "updated_at")
    autocomplete_fields = ("organization",)


@admin.register(OrganizationMembership)
class OrganizationMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "organization", "is_active", "created_at")
    list_filter = ("is_active", "organization")
    search_fields = ("user__username", "user__email", "organization__display_name")
    readonly_fields = ("id", "created_at", "updated_at")
    autocomplete_fields = ("user", "organization")


@admin.register(ClinicMembership)
class ClinicMembershipAdmin(admin.ModelAdmin):
    list_display = ("organization_membership", "clinic", "is_active", "created_at")
    list_filter = ("is_active", "clinic__organization")
    search_fields = (
        "organization_membership__user__username",
        "organization_membership__organization__display_name",
        "clinic__name",
    )
    readonly_fields = ("id", "created_at", "updated_at")
    autocomplete_fields = ("organization_membership", "clinic")
