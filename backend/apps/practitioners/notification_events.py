from apps.accounts.models import Notification, Role
from apps.accounts.notification_services import notify_owners, notify_user


def notify_application_submitted(application):
    common = dict(
        organization=application.organization,
        category=Notification.Category.PRACTITIONERS,
        related_object_type="practitioner_application",
        related_object_id=application.id,
    )
    notify_owners(
        **common,
        notification_type="PRACTITIONER_APPLICATION_SUBMITTED",
        title="New practitioner application",
        message="A practitioner application is ready for review.",
        target_url="/owner#practitioner-applications",
        action_required=True,
        dedupe_key=f"practitioner-application:{application.id}:submitted:{application.status}",
    )
    notify_user(
        **common,
        recipient=application.applicant,
        recipient_role=Role.PHYSIOTHERAPIST,
        notification_type="APPLICATION_RECEIVED",
        title="Application received",
        message="Your practitioner application was submitted successfully.",
        target_url="/practitioner-application",
        dedupe_key=f"practitioner-application:{application.id}:received:{application.status}",
    )


def notify_application_decision(application):
    titles = {
        "CORRECTION_REQUIRED": "Additional information required",
        "REJECTED": "Application not approved",
        "APPROVED": "Application approved",
    }
    title = titles.get(application.status)
    if title is None:
        return
    notify_user(
        organization=application.organization,
        recipient=application.applicant,
        recipient_role=Role.PHYSIOTHERAPIST,
        notification_type=f"APPLICATION_{application.status}",
        category=Notification.Category.PRACTITIONERS,
        title=title,
        message=(
            "Your practitioner account is ready."
            if application.status == "APPROVED"
            else "Open your application to review the decision and next steps."
        ),
        related_object_type="practitioner_application",
        related_object_id=application.id,
        target_url=("/physiotherapist" if application.status == "APPROVED" else "/practitioner-application"),
        action_required=application.status == "CORRECTION_REQUIRED",
        dedupe_key=f"practitioner-application:{application.id}:decision:{application.status}",
    )
