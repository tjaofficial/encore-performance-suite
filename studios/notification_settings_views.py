from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from communications.notification_services import notification_preference_for
from studios.models import Studio, StudioMembership


def _notification_settings_role(request, studio):
    role = request.session.get("encore_workspace_role")

    if request.session.get("encore_workspace_studio_slug") != studio.slug:
        return None

    if request.user.is_superuser and role == StudioMembership.Role.ADMINISTRATOR:
        return role

    if role not in {
        StudioMembership.Role.ADMINISTRATOR,
        StudioMembership.Role.TEACHER,
    }:
        return None

    if request.user.studio_memberships.filter(
        studio=studio,
        role=role,
        is_active=True,
    ).exists():
        return role

    return None


@login_required
def notification_settings(request, studio_slug):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role = _notification_settings_role(request, studio)

    if role is None:
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    preference = notification_preference_for(
        request.user,
        studio,
    )

    if request.method == "POST":
        boolean_fields = [
            "task_assigned",
            "task_reassigned",
            "task_due_reminder",
            "task_overdue",
            "task_creator_completed",
        ]

        if role == StudioMembership.Role.ADMINISTRATOR:
            boolean_fields.extend([
                "registration_new",
                "extra_work_logged",
            ])

        for field_name in boolean_fields:
            setattr(
                preference,
                field_name,
                request.POST.get(field_name) == "on",
            )

        try:
            reminder_days = int(
                request.POST.get(
                    "task_due_reminder_days",
                    preference.task_due_reminder_days,
                )
            )
        except (TypeError, ValueError):
            reminder_days = 2

        preference.task_due_reminder_days = max(0, min(reminder_days, 30))
        preference.save()

        messages.success(
            request,
            "Notification settings saved.",
        )

        return redirect(
            "studios:notification_settings",
            studio_slug=studio.slug,
        )

    return render(
        request,
        "studios/notification_settings.html",
        {
            "studio": studio,
            "role": role,
            "settings_section": "notifications",
            "notification_preference": preference,
        },
    )
