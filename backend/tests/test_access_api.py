import pytest
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Role, RoleAssignment, RoleAuditEvent, User
from apps.tenancy.models import (
    Clinic,
    ClinicMembership,
    Organization,
    OrganizationMembership,
)


@pytest.fixture
def access_context(db):
    organization = Organization.objects.create(
        legal_name="JeevaSetu", display_name="JeevaSetu", slug="jeevasetu"
    )
    north = Clinic.objects.create(organization=organization, name="North", slug="north")
    south = Clinic.objects.create(organization=organization, name="South", slug="south")
    return organization, north, south


def create_member(username, organization, clinics=(), **user_fields):
    user = User.objects.create_user(
        username=username, password="Strong-Test-Password-42!", **user_fields
    )
    membership = OrganizationMembership.objects.create(user=user, organization=organization)
    clinic_memberships = {
        clinic.id: ClinicMembership.objects.create(
            organization_membership=membership, clinic=clinic
        )
        for clinic in clinics
    }
    return user, membership, clinic_memberships


def create_assignment(user, membership, role, organization, clinic=None, *, active=True):
    clinic_membership = None
    if clinic is not None:
        clinic_membership = ClinicMembership.objects.filter(
            organization_membership=membership, clinic=clinic
        ).first()
    value = RoleAssignment(
        user=user,
        organization=organization,
        organization_membership=membership,
        clinic=clinic,
        clinic_membership=clinic_membership,
        role=role,
        is_active=active,
        disabled_at=None if active else timezone.now(),
        disabled_reason="" if active else "temporarily disabled",
    )
    value.full_clean()
    value.save()
    return value


def authenticate(api_client, user, organization):
    api_client.force_authenticate(user)
    api_client.credentials(HTTP_X_ORGANIZATION_SLUG=organization.slug)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("role", "clinic_scoped"),
    [
        (Role.OWNER, False),
        (Role.MANAGER, True),
        (Role.PHYSIOTHERAPIST, True),
        (Role.CUSTOMER, False),
    ],
)
def test_access_summary_returns_only_active_caller_scope(
    api_client, access_context, role, clinic_scoped
):
    organization, north, _ = access_context
    user, membership, _ = create_member(role.lower(), organization, (north,))
    assignment = create_assignment(
        user, membership, role, organization, north if clinic_scoped else None
    )
    authenticate(api_client, user, organization)

    response = api_client.get("/api/v1/access/me/")

    assert response.status_code == 200
    assert response.data["user_id"] == str(user.id)
    assert response.data["organization"] == {"id": str(organization.id), "slug": "jeevasetu"}
    assert [item["id"] for item in response.data["roles"]] == [str(assignment.id)]
    assert "email" not in response.data
    assert "token" not in response.data


@pytest.mark.django_db
@pytest.mark.parametrize("disabled", ["user", "membership", "role", "organization", "clinic"])
def test_access_summary_denies_disabled_authorization_chain(api_client, access_context, disabled):
    organization, north, _ = access_context
    user, membership, _ = create_member("disabled", organization, (north,))
    role = create_assignment(user, membership, Role.PHYSIOTHERAPIST, organization, north)
    obj = {
        "user": user,
        "membership": membership,
        "role": role,
        "organization": organization,
        "clinic": north,
    }[disabled]
    if disabled == "user":
        obj.is_enabled = False
    else:
        obj.is_active = False
    if disabled == "role":
        obj.disabled_at = timezone.now()
    obj.save()
    authenticate(api_client, user, organization)

    response = api_client.get("/api/v1/access/me/")

    assert response.status_code in (403, 404)


@pytest.mark.django_db
def test_access_requires_jwt_and_valid_tenant(api_client, access_context):
    organization, _, _ = access_context
    assert api_client.get("/api/v1/access/me/").status_code == 401
    user, membership, _ = create_member("owner", organization)
    create_assignment(user, membership, Role.OWNER, organization)
    token = str(RefreshToken.for_user(user).access_token)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}", HTTP_X_ORGANIZATION_SLUG="unknown")
    assert api_client.get("/api/v1/access/me/").status_code == 404


@pytest.mark.django_db
def test_role_listing_enforces_owner_manager_and_self_visibility(api_client, access_context):
    organization, north, south = access_context
    owner, owner_membership, _ = create_member("owner", organization)
    manager, manager_membership, _ = create_member("manager", organization, (north,))
    physio, physio_membership, _ = create_member("physio", organization, (north, south))
    customer, customer_membership, _ = create_member("customer", organization)
    create_assignment(owner, owner_membership, Role.OWNER, organization)
    create_assignment(manager, manager_membership, Role.MANAGER, organization, north)
    north_role = create_assignment(
        physio, physio_membership, Role.PHYSIOTHERAPIST, organization, north
    )
    create_assignment(physio, physio_membership, Role.PHYSIOTHERAPIST, organization, south)
    customer_role = create_assignment(customer, customer_membership, Role.CUSTOMER, organization)

    authenticate(api_client, owner, organization)
    assert len(api_client.get("/api/v1/access/roles/").data) == 5
    authenticate(api_client, manager, organization)
    assert [item["id"] for item in api_client.get("/api/v1/access/roles/").data] == [
        str(north_role.id)
    ]
    authenticate(api_client, physio, organization)
    assert len(api_client.get("/api/v1/access/roles/").data) == 2
    authenticate(api_client, customer, organization)
    assert [item["id"] for item in api_client.get("/api/v1/access/roles/").data] == [
        str(customer_role.id)
    ]


@pytest.mark.django_db
def test_owner_creates_each_supported_role(api_client, access_context):
    organization, north, _ = access_context
    owner, owner_membership, _ = create_member("owner", organization)
    create_assignment(owner, owner_membership, Role.OWNER, organization)
    authenticate(api_client, owner, organization)

    for role in Role.values:
        target, _, _ = create_member(f"target-{role.lower()}", organization, (north,))
        payload = {"user_id": str(target.id), "role": role}
        if role == Role.PHYSIOTHERAPIST:
            payload["clinic_id"] = str(north.id)
        response = api_client.post("/api/v1/access/roles/", payload, format="json")
        assert response.status_code == 201, response.data

    assert RoleAuditEvent.objects.filter(event=RoleAuditEvent.Event.ASSIGNED).count() == 4


@pytest.mark.django_db
@pytest.mark.parametrize("role", [Role.PHYSIOTHERAPIST, Role.CUSTOMER])
def test_manager_creates_only_delegated_roles(api_client, access_context, role):
    organization, north, _ = access_context
    manager, manager_membership, _ = create_member("manager", organization, (north,))
    create_assignment(manager, manager_membership, Role.MANAGER, organization, north)
    target, _, _ = create_member(f"target-{role.lower()}", organization, (north,))
    authenticate(api_client, manager, organization)

    response = api_client.post(
        "/api/v1/access/roles/",
        {"user_id": str(target.id), "role": role, "clinic_id": str(north.id)},
        format="json",
    )

    assert response.status_code == 201


@pytest.mark.django_db
@pytest.mark.parametrize("forbidden_role", [Role.OWNER, Role.MANAGER, "SUPER_ADMIN"])
def test_manager_escalation_is_denied_and_audited(api_client, access_context, forbidden_role):
    organization, north, _ = access_context
    manager, manager_membership, _ = create_member("manager", organization, (north,))
    create_assignment(manager, manager_membership, Role.MANAGER, organization, north)
    target, _, _ = create_member("target", organization, (north,))
    authenticate(api_client, manager, organization)

    response = api_client.post(
        "/api/v1/access/roles/",
        {"user_id": str(target.id), "role": forbidden_role, "clinic_id": str(north.id)},
        format="json",
    )

    assert response.status_code in (400, 403)
    assert RoleAuditEvent.objects.filter(event=RoleAuditEvent.Event.PRIVILEGE_ESCALATION).exists()


@pytest.mark.django_db
def test_manager_self_promotion_is_denied_and_audited(api_client, access_context):
    organization, north, _ = access_context
    manager, manager_membership, _ = create_member("manager", organization, (north,))
    create_assignment(manager, manager_membership, Role.MANAGER, organization, north)
    authenticate(api_client, manager, organization)

    response = api_client.post(
        "/api/v1/access/roles/",
        {
            "user_id": str(manager.id),
            "role": Role.CUSTOMER,
            "clinic_id": str(north.id),
        },
        format="json",
    )

    assert response.status_code == 403
    assert RoleAuditEvent.objects.filter(event=RoleAuditEvent.Event.PRIVILEGE_ESCALATION).exists()


@pytest.mark.django_db
def test_non_managers_cannot_create_roles(api_client, access_context):
    organization, north, _ = access_context
    target, _, _ = create_member("target", organization, (north,))
    for role in (Role.PHYSIOTHERAPIST, Role.CUSTOMER):
        actor, membership, _ = create_member(f"actor-{role.lower()}", organization, (north,))
        create_assignment(
            actor, membership, role, organization, north if role == Role.PHYSIOTHERAPIST else None
        )
        authenticate(api_client, actor, organization)
        response = api_client.post(
            "/api/v1/access/roles/",
            {"user_id": str(target.id), "role": Role.CUSTOMER},
            format="json",
        )
        assert response.status_code == 403


@pytest.mark.django_db
def test_duplicate_disabled_and_cross_tenant_assignments_are_rejected(api_client, access_context):
    organization, north, _ = access_context
    owner, owner_membership, _ = create_member("owner", organization)
    create_assignment(owner, owner_membership, Role.OWNER, organization)
    target, target_membership, _ = create_member("target", organization)
    create_assignment(target, target_membership, Role.CUSTOMER, organization)
    authenticate(api_client, owner, organization)
    duplicate = api_client.post(
        "/api/v1/access/roles/", {"user_id": str(target.id), "role": Role.CUSTOMER}, format="json"
    )
    assert duplicate.status_code == 400

    disabled, _, _ = create_member("disabled", organization, is_enabled=False)
    response = api_client.post(
        "/api/v1/access/roles/", {"user_id": str(disabled.id), "role": Role.CUSTOMER}, format="json"
    )
    assert response.status_code == 400

    other = Organization.objects.create(legal_name="Other", display_name="Other", slug="other")
    outsider, _, _ = create_member("outsider", other)
    response = api_client.post(
        "/api/v1/access/roles/", {"user_id": str(outsider.id), "role": Role.CUSTOMER}, format="json"
    )
    assert response.status_code == 400
    assert RoleAuditEvent.objects.filter(event=RoleAuditEvent.Event.CROSS_TENANT).exists()


@pytest.mark.django_db
def test_manager_cannot_escape_clinic_scope(api_client, access_context):
    organization, north, south = access_context
    manager, manager_membership, _ = create_member("manager", organization, (north,))
    create_assignment(manager, manager_membership, Role.MANAGER, organization, north)
    target, _, _ = create_member("target", organization, (south,))
    authenticate(api_client, manager, organization)

    response = api_client.post(
        "/api/v1/access/roles/",
        {"user_id": str(target.id), "role": Role.PHYSIOTHERAPIST, "clinic_id": str(south.id)},
        format="json",
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_manager_cannot_use_or_list_an_inactive_clinic_scope(api_client, access_context):
    organization, north, south = access_context
    manager, manager_membership, _ = create_member("manager", organization, (north, south))
    create_assignment(manager, manager_membership, Role.MANAGER, organization, north)
    create_assignment(manager, manager_membership, Role.MANAGER, organization, south)
    physio, physio_membership, _ = create_member("physio", organization, (south,))
    hidden = create_assignment(physio, physio_membership, Role.PHYSIOTHERAPIST, organization, south)
    south.is_active = False
    south.save(update_fields=("is_active",))
    authenticate(api_client, manager, organization)

    response = api_client.get("/api/v1/access/roles/")

    assert response.status_code == 200
    assert str(hidden.id) not in {item["id"] for item in response.data}


@pytest.mark.django_db
def test_invalid_other_organization_clinic_is_rejected(api_client, access_context):
    organization, _, _ = access_context
    owner, owner_membership, _ = create_member("owner", organization)
    create_assignment(owner, owner_membership, Role.OWNER, organization)
    target, _, _ = create_member("target", organization)
    other = Organization.objects.create(legal_name="Other", display_name="Other", slug="other")
    other_clinic = Clinic.objects.create(organization=other, name="Other", slug="other")
    authenticate(api_client, owner, organization)

    response = api_client.post(
        "/api/v1/access/roles/",
        {
            "user_id": str(target.id),
            "role": Role.PHYSIOTHERAPIST,
            "clinic_id": str(other_clinic.id),
        },
        format="json",
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_owner_updates_clinic_scope_without_mutating_role(api_client, access_context):
    organization, north, south = access_context
    owner, owner_membership, _ = create_member("owner", organization)
    create_assignment(owner, owner_membership, Role.OWNER, organization)
    physio, physio_membership, _ = create_member("physio", organization, (north, south))
    value = create_assignment(physio, physio_membership, Role.PHYSIOTHERAPIST, organization, north)
    authenticate(api_client, owner, organization)

    response = api_client.patch(
        f"/api/v1/access/roles/{value.id}/", {"clinic_id": str(south.id)}, format="json"
    )
    unsafe = api_client.patch(
        f"/api/v1/access/roles/{value.id}/", {"role": Role.OWNER}, format="json"
    )

    assert response.status_code == 200
    assert response.data["clinic_id"] == str(south.id)
    assert unsafe.status_code == 400
    assert RoleAuditEvent.objects.filter(event=RoleAuditEvent.Event.CHANGED).exists()


@pytest.mark.django_db
def test_deactivation_activation_and_idempotency_are_audited(api_client, access_context):
    organization, north, _ = access_context
    owner, owner_membership, _ = create_member("owner", organization)
    create_assignment(owner, owner_membership, Role.OWNER, organization)
    physio, physio_membership, _ = create_member("physio", organization, (north,))
    value = create_assignment(physio, physio_membership, Role.PHYSIOTHERAPIST, organization, north)
    authenticate(api_client, owner, organization)

    deactivate_url = f"/api/v1/access/roles/{value.id}/deactivate/"
    activate_url = f"/api/v1/access/roles/{value.id}/activate/"
    assert (
        api_client.post(deactivate_url, {"reason": "access ended"}, format="json").status_code
        == 200
    )
    assert (
        api_client.post(deactivate_url, {"reason": "access ended"}, format="json").status_code
        == 200
    )
    assert api_client.post(activate_url, {}, format="json").status_code == 200
    assert api_client.post(activate_url, {}, format="json").status_code == 200
    assert RoleAuditEvent.objects.filter(event=RoleAuditEvent.Event.DISABLED).count() == 1
    assert RoleAuditEvent.objects.filter(event=RoleAuditEvent.Event.ACTIVATED).count() == 1


@pytest.mark.django_db
def test_manager_deactivates_physio_in_scope_but_self_roles_cannot_manage(
    api_client, access_context
):
    organization, north, _ = access_context
    manager, manager_membership, _ = create_member("manager", organization, (north,))
    create_assignment(manager, manager_membership, Role.MANAGER, organization, north)
    physio, physio_membership, _ = create_member("physio", organization, (north,))
    physio_role = create_assignment(
        physio, physio_membership, Role.PHYSIOTHERAPIST, organization, north
    )
    url = f"/api/v1/access/roles/{physio_role.id}/deactivate/"
    authenticate(api_client, manager, organization)
    assert api_client.post(url, {"reason": "assignment ended"}, format="json").status_code == 200

    customer, customer_membership, _ = create_member("customer", organization)
    customer_role = create_assignment(customer, customer_membership, Role.CUSTOMER, organization)
    authenticate(api_client, customer, organization)
    response = api_client.post(
        f"/api/v1/access/roles/{customer_role.id}/deactivate/",
        {"reason": "not allowed"},
        format="json",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_final_owner_and_manager_owner_deactivation_are_denied_and_audited(
    api_client, access_context
):
    organization, north, _ = access_context
    owner, owner_membership, _ = create_member("owner", organization)
    owner_role = create_assignment(owner, owner_membership, Role.OWNER, organization)
    authenticate(api_client, owner, organization)
    url = f"/api/v1/access/roles/{owner_role.id}/deactivate/"
    assert api_client.post(url, {"reason": "remove"}, format="json").status_code == 403
    assert RoleAuditEvent.objects.filter(event=RoleAuditEvent.Event.FINAL_OWNER).exists()

    manager, manager_membership, _ = create_member("manager", organization, (north,))
    create_assignment(manager, manager_membership, Role.MANAGER, organization, north)
    authenticate(api_client, manager, organization)
    assert api_client.post(url, {"reason": "remove"}, format="json").status_code == 404
    assert RoleAuditEvent.objects.filter(event=RoleAuditEvent.Event.PRIVILEGE_ESCALATION).exists()


@pytest.mark.django_db
def test_cross_tenant_detail_is_not_disclosed_and_is_audited(api_client, access_context):
    organization, _, _ = access_context
    owner, owner_membership, _ = create_member("owner", organization)
    create_assignment(owner, owner_membership, Role.OWNER, organization)
    other = Organization.objects.create(legal_name="Other", display_name="Other", slug="other")
    outsider, outsider_membership, _ = create_member("outsider", other)
    hidden = create_assignment(outsider, outsider_membership, Role.CUSTOMER, other)
    authenticate(api_client, owner, organization)

    response = api_client.get(f"/api/v1/access/roles/{hidden.id}/")

    assert response.status_code == 404
    assert response.data == {"detail": "Role assignment is unavailable."}
    assert RoleAuditEvent.objects.filter(event=RoleAuditEvent.Event.CROSS_TENANT).exists()


@pytest.mark.django_db
def test_role_response_contains_no_sensitive_identity_fields(api_client, access_context):
    organization, _, _ = access_context
    owner, owner_membership, _ = create_member("owner", organization)
    create_assignment(owner, owner_membership, Role.OWNER, organization)
    authenticate(api_client, owner, organization)

    payload = str(api_client.get("/api/v1/access/roles/").data).lower()

    assert all(field not in payload for field in ("password", "email", "mobile_number", "token"))
