import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)

from accounts.dashboard_layouts import (
    class_dashboard_editor_cards,
    default_class_dashboard_layout,
    normalize_class_dashboard_layout,
)
from accounts.models import DashboardPreference
from studios.dashboard_quick_links_support import (
    parse_quick_links_post,
    quick_links_context,
)
from studios.models import Studio


def _class_settings_role(
    request,
    studio,
):
    role = request.session.get(
        "encore_workspace_role"
    )

    if (
        request.session.get(
            "encore_workspace_studio_slug"
        )
        != studio.slug
    ):
        return None

    if (
        request.user.is_superuser
        and role == "administrator"
    ):
        return role

    if role not in {
        "administrator",
        "teacher",
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
def class_dashboard_settings(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role = _class_settings_role(
        request,
        studio,
    )

    if role is None:
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
                .CLASS
            ),
            defaults={
                "layout": (
                    default_class_dashboard_layout()
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
                default_class_dashboard_layout()
            )

            preference.save(
                update_fields=[
                    "layout",
                    "updated_at",
                ]
            )

            messages.success(
                request,
                "Class Dashboard layout reset to default.",
            )

            return redirect(
                "studios:class_dashboard_settings",
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
                default_class_dashboard_layout()
            )

        if not isinstance(
            submitted,
            dict,
        ):
            submitted = {}

        submitted["quick_links"] = (
            parse_quick_links_post(
                request,
                dashboard_kind="class",
            )
        )

        preference.layout = (
            normalize_class_dashboard_layout(
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
            "Class Dashboard layout saved.",
        )

        return redirect(
            "studios:class_dashboard_settings",
            studio_slug=studio.slug,
        )

    layout = normalize_class_dashboard_layout(
        preference.layout
    )

    context = {
        "studio": studio,
        "role": role,
        "settings_section": "class_dashboard",
        "editor_cards": (
            class_dashboard_editor_cards(
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
            dashboard_kind="class",
        )
    )

    return render(
        request,
        "studios/class_dashboard_settings.html",
        context,
    )
