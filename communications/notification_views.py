from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

from studios.models import Studio

from .models import AnnouncementRead
from tasks.models import TaskNotification
from .services import visible_announcements_for_user, workspace_role


@login_required
def notification_center(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role = workspace_role(
        request,
        studio,
    )

    if role is None:
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    announcements = (
        visible_announcements_for_user(
            request,
            studio,
        )
        .order_by(
            "-is_pinned",
            "-publish_at",
        )
    )

    read_ids = set(
        AnnouncementRead.objects.filter(
            user=request.user,
            announcement__in=announcements,
        ).values_list(
            "announcement_id",
            flat=True,
        )
    )

    rows = [
        {
            "announcement": item,
            "is_read": item.id in read_ids,
        }
        for item in announcements
    ]

    task_notifications = (
        TaskNotification.objects
        .filter(
            studio=studio,
            user=request.user,
        )
        .select_related(
            "task",
        )
        .order_by(
            "-created_at",
        )[:20]
    )

    return render(
        request,
        "communications/notification_center.html",
        {
            "studio": studio,
            "role": role,
            "notification_rows": rows,
            "task_notifications": task_notifications,
        },
    )
