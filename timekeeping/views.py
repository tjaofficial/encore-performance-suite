from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)

from studios.models import Studio, StudioMembership

from .forms import ExtraWorkEntryForm
from .models import ExtraWorkEntry


def _teacher_workspace(
    request,
    studio,
):
    role = request.session.get(
        "encore_workspace_role"
    )

    studio_slug = request.session.get(
        "encore_workspace_studio_slug"
    )

    if (
        role != StudioMembership.Role.TEACHER
        or studio_slug != studio.slug
    ):
        return False

    return request.user.studio_memberships.filter(
        studio=studio,
        role=StudioMembership.Role.TEACHER,
        is_active=True,
    ).exists()


@login_required
def extra_work_list(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if not _teacher_workspace(
        request,
        studio,
    ):
        return render(
            request,
            "dashboard/access_denied.html",
            {
                "studio": studio,
            },
            status=403,
        )

    today = date.today()

    default_start = today.replace(
        day=1,
    )

    if today.month == 12:
        next_month = date(
            today.year + 1,
            1,
            1,
        )
    else:
        next_month = date(
            today.year,
            today.month + 1,
            1,
        )

    default_end = (
        next_month
        - timedelta(days=1)
    )

    start_value = (
        request.GET.get("start")
        or default_start.isoformat()
    )

    end_value = (
        request.GET.get("end")
        or default_end.isoformat()
    )

    try:
        start_date = date.fromisoformat(
            start_value
        )
    except ValueError:
        start_date = default_start
        start_value = default_start.isoformat()

    try:
        end_date = date.fromisoformat(
            end_value
        )
    except ValueError:
        end_date = default_end
        end_value = default_end.isoformat()

    if start_date > end_date:
        start_date, end_date = (
            end_date,
            start_date,
        )

        start_value = start_date.isoformat()
        end_value = end_date.isoformat()

    entries = (
        ExtraWorkEntry.objects
        .filter(
            studio=studio,
            user=request.user,
            work_date__gte=start_date,
            work_date__lte=end_date,
        )
        .order_by(
            "-work_date",
            "-created_at",
        )
    )

    total_minutes = sum(
        entry.duration_minutes
        for entry in entries
    )

    total_hours = total_minutes // 60
    total_remaining_minutes = (
        total_minutes % 60
    )

    if (
        total_hours
        and total_remaining_minutes
    ):
        total_duration_display = (
            f"{total_hours}h "
            f"{total_remaining_minutes}m"
        )
    elif total_hours:
        total_duration_display = (
            f"{total_hours}h"
        )
    else:
        total_duration_display = (
            f"{total_remaining_minutes}m"
        )

    return render(
        request,
        "timekeeping/extra_work_list.html",
        {
            "studio": studio,
            "role": "teacher",
            "entries": entries,
            "start_date": start_value,
            "end_date": end_value,
            "total_duration_display": (
                total_duration_display
            ),
        },
    )


@login_required
def extra_work_create(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if not _teacher_workspace(
        request,
        studio,
    ):
        return render(
            request,
            "dashboard/access_denied.html",
            {
                "studio": studio,
            },
            status=403,
        )

    form = ExtraWorkEntryForm(
        request.POST or None,
        studio=studio,
        user=request.user,
    )

    if (
        request.method == "POST"
        and form.is_valid()
    ):
        form.save()

        messages.success(
            request,
            "Extra work was logged.",
        )

        return redirect(
            "timekeeping:extra_work_list",
            studio_slug=studio.slug,
        )

    return render(
        request,
        "timekeeping/extra_work_form.html",
        {
            "studio": studio,
            "role": "teacher",
            "form": form,
        },
    )
