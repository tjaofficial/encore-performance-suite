from django.utils import timezone

from studios.models import Studio
from tasks.models import TaskNotification

from .models import AnnouncementRead, WorkspaceNotification
from .services import visible_announcements_for_user


ROLE_LABELS = {
    "administrator": "Administrator",
    "teacher": "Teacher",
    "family": "Parent / Guardian",
    "student": "Student",
}


def workspace_notifications(request):
    if not request.user.is_authenticated:
        return {}

    studio_slug = request.session.get(
        "encore_workspace_studio_slug"
    )
    role = request.session.get(
        "encore_workspace_role"
    )

    membership_count = (
        request.user.studio_memberships
        .filter(
            is_active=True,
            studio__is_active=True,
        )
        .count()
    )

    now = timezone.localtime()
    today = timezone.localdate()

    if now.hour < 12:
        greeting = "Good morning"
    elif now.hour < 17:
        greeting = "Good afternoon"
    else:
        greeting = "Good evening"

    display_name = (
        request.user.first_name
        or request.user.username
        or request.user.email
    )

    shell_context = {
        "encore_workspace_membership_count": membership_count,
        "encore_has_multiple_workspaces": membership_count > 1,
        "encore_workspace_role_label": ROLE_LABELS.get(
            role,
            role.replace("_", " ").title() if role else "",
        ),
        "encore_shell_greeting": greeting,
        "encore_shell_name": display_name,
        "encore_shell_date": today,
        "encore_shell_subtitle": "",
    }

    if not studio_slug:
        return shell_context

    studio = Studio.objects.filter(
        slug=studio_slug,
        is_active=True,
    ).first()

    if studio is None:
        return shell_context

    shell_context["encore_shell_subtitle"] = (
        f"Here's what's happening at {studio.name} today."
    )

    visible = visible_announcements_for_user(
        request,
        studio,
    )

    latest = list(
        visible.order_by(
            "-is_pinned",
            "-publish_at",
        )[:4]
    )

    read_ids = set(
        AnnouncementRead.objects.filter(
            user=request.user,
            announcement__in=latest,
        ).values_list(
            "announcement_id",
            flat=True,
        )
    )

    unread_announcement_count = (
        visible.exclude(
            read_receipts__user=request.user,
        )
        .distinct()
        .count()
    )

    unread_task_count = (
        TaskNotification.objects
        .filter(
            studio=studio,
            user=request.user,
            read_at__isnull=True,
        )
        .count()
    )

    unread_workspace_count = (
        WorkspaceNotification.objects
        .filter(
            studio=studio,
            user=request.user,
            read_at__isnull=True,
        )
        .count()
    )

    shell_context.update({
        "encore_notification_studio": studio,
        "encore_latest_announcements": [
            {
                "announcement": item,
                "is_read": item.id in read_ids,
            }
            for item in latest
        ],
        "encore_unread_notification_count": (
            unread_announcement_count
            + unread_task_count
            + unread_workspace_count
        ),
    })

    return shell_context
