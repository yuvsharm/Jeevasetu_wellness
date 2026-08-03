from rest_framework import serializers

from apps.tenancy.models import Clinic, Organization


class OrganizationContextSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ("id", "display_name", "slug", "timezone", "default_currency")
        read_only_fields = fields


class ClinicSerializer(serializers.ModelSerializer):
    class Meta:
        model = Clinic
        fields = ("id", "name", "slug", "timezone")
        read_only_fields = fields
