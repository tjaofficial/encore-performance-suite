from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from studios.models import Studio
from dashboard.parent_portal import parent_portal_context

from .models import AnnouncementRead, WorkspaceNotification
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

    if role == "family":
        owned = WorkspaceNotification.objects.filter(studio=studio, user=request.user)
        # GET only reads an item when explicitly clicked, never on dropdown display.
        opened_id = request.GET.get("open", "")
        if opened_id.isdigit():
            item = get_object_or_404(owned, pk=int(opened_id))
            if item.read_at is None:
                owned.filter(pk=item.pk, read_at__isnull=True).update(read_at=timezone.now())
            if item.action_url.startswith("/") and not item.action_url.startswith("//") and "\\" not in item.action_url:
                return redirect(item.action_url)
            return redirect("communications:notification_center", studio_slug=studio.slug)

        if request.method == "POST":
            operation = request.POST.get("operation")
            if operation == "mark_all_read":
                owned.filter(read_at__isnull=True).update(read_at=timezone.now())
            elif operation == "mark_read":
                item_id = request.POST.get("notification_id", "")
                if item_id.isdigit():
                    owned.filter(pk=int(item_id), read_at__isnull=True).update(read_at=timezone.now())
            return redirect("communications:notification_center", studio_slug=studio.slug)

        unread_only = request.GET.get("filter") == "unread"
        shown = owned.filter(read_at__isnull=True) if unread_only else owned
        context = {
            **parent_portal_context(request, studio, section="notifications"),
            "studio": studio, "role": role,
            "workspace_notifications": shown.order_by("-created_at", "-pk")[:100],
            "notification_filter": "unread" if unread_only else "all",
        }
        return render(request, "communications/parent_notification_center.html", context)

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

    workspace_notifications = (
        WorkspaceNotification.objects
        .filter(
            studio=studio,
            user=request.user,
        )
        .order_by(
            "-created_at",
        )[:30]
    )

    context = {
        "studio": studio,
        "role": role,
        "notification_rows": rows,
        "task_notifications": task_notifications,
        "workspace_notifications": workspace_notifications,
    }

    template_name = "communications/notification_center.html"

    if role == "family":
        context.update(
            parent_portal_context(
                request,
                studio,
                section="notifications",
            )
        )
        template_name = (
            "communications/parent_notification_center.html"
        )

    return render(
        request,
        template_name,
        context,
    )


@login_required
def workspace_notification_open(
    request,
    studio_slug,
    notification_id,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role = workspace_role(request, studio)
    if role is None:
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    item = get_object_or_404(
        WorkspaceNotification,
        pk=notification_id,
        studio=studio,
        user=request.user,
    )

    if item.read_at is None:
        from django.utils import timezone
        item.read_at = timezone.now()
        item.save(update_fields=["read_at"])

    if item.action_url and item.action_url.startswith("/"):
        return redirect(item.action_url)

    return redirect(
        "communications:notification_center",
        studio_slug=studio.slug,
    )
