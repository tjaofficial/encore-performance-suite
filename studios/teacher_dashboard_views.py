import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)

from accounts.models import DashboardPreference
from accounts.teacher_dashboard_layouts import (
    default_teacher_dashboard_layout,
    normalize_teacher_dashboard_layout,
    teacher_dashboard_editor_cards,
)
from studios.dashboard_quick_links_support import (
    parse_quick_links_post,
    quick_links_context,
)
from studios.models import Studio


def _teacher_workspace(
    request,
    studio,
):
    return (
        request.session.get(
            "encore_workspace_role"
        )
        == "teacher"
        and request.session.get(
            "encore_workspace_studio_slug"
        )
        == studio.slug
        and request.user.studio_memberships.filter(
            studio=studio,
            role="teacher",
            is_active=True,
        ).exists()
    )


@login_required
def teacher_dashboard_settings(
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

    preference, _created = (
        DashboardPreference.objects
        .get_or_create(
            user=request.user,
            studio=studio,
            dashboard_type=(
                DashboardPreference
                .DashboardType
                .TEACHER
            ),
            defaults={
                "layout": (
                    default_teacher_dashboard_layout()
                ),
            },
        )
    )

    if request.method == "POST":
        action = request.POST.get(
            "action",
            "save",
        )

        if action == "reset":
            preference.layout = (
                default_teacher_dashboard_layout()
            )

            preference.save(
                update_fields=[
                    "layout",
                    "updated_at",
                ]
            )

            messages.success(
                request,
                "Teacher Dashboard reset to the default layout.",
            )

            return redirect(
                "studios:teacher_dashboard_settings",
                studio_slug=studio.slug,
            )

        try:
            submitted = json.loads(
                request.POST.get(
                    "layout_json",
                    "",
                )
            )
        except (
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ):
            submitted = (
                default_teacher_dashboard_layout()
            )

        if not isinstance(
            submitted,
            dict,
        ):
            submitted = {}

        submitted["quick_links"] = (
            parse_quick_links_post(
                request,
                dashboard_kind="teacher",
            )
        )

        preference.layout = (
            normalize_teacher_dashboard_layout(
                submitted
            )
        )

        preference.save(
            update_fields=[
                "layout",
                "updated_at",
            ]
        )

        messages.success(
            request,
            "Teacher Dashboard layout saved.",
        )

        return redirect(
            "studios:teacher_dashboard_settings",
            studio_slug=studio.slug,
        )

    layout = (
        normalize_teacher_dashboard_layout(
            preference.layout
        )
    )

    context = {
        "studio": studio,
        "role": "teacher",
        "settings_section": "teacher_dashboard",
        "editor_cards": (
            teacher_dashboard_editor_cards(
                layout
            )
        ),
        "layout_json": json.dumps(
            layout
        ),
    }

    context.update(
        quick_links_context(
            layout,
            dashboard_kind="teacher",
        )
    )

    return render(
        request,
        "studios/teacher_dashboard_settings.html",
        context,
    )
