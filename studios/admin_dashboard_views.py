import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)

from accounts.models import DashboardPreference
from dashboard.admin_dashboard_layouts import (
    admin_dashboard_editor_cards,
    admin_snapshot_metric_options,
    default_admin_dashboard_layout,
    normalize_admin_dashboard_layout,
)
from studios.dashboard_quick_links_support import (
    parse_quick_links_post,
    quick_links_context,
)
from studios.models import Studio


@login_required
def admin_dashboard_settings(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    has_access = (
        request.user.is_superuser
        or request.user.studio_memberships.filter(
            studio=studio,
            role="administrator",
            is_active=True,
        ).exists()
    )

    if not has_access:
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    preference, _created = (
        DashboardPreference.objects
        .get_or_create(
            user=request.user,
            studio=studio,
            dashboard_type=DashboardPreference.DashboardType.ADMIN,
            defaults={"layout": default_admin_dashboard_layout()},
        )
    )

    if request.method == "POST":
        action = request.POST.get("action", "save")

        if action == "reset":
            preference.layout = default_admin_dashboard_layout()
            preference.save(update_fields=["layout", "updated_at"])

            messages.success(
                request,
                "Admin Dashboard layout reset to default.",
            )

            return redirect(
                "studios:admin_dashboard_settings",
                studio_slug=studio.slug,
            )

        try:
            submitted = json.loads(
                request.POST.get("layout_json", "")
            )
        except (
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ):
            submitted = default_admin_dashboard_layout()

        if not isinstance(
            submitted,
            dict,
        ):
            submitted = {}

        submitted["quick_links"] = (
            parse_quick_links_post(
                request,
                dashboard_kind="admin",
            )
        )

        preference.layout = normalize_admin_dashboard_layout(
            submitted
        )
        preference.save(update_fields=["layout", "updated_at"])

        messages.success(
            request,
            "Admin Dashboard layout saved.",
        )

        return redirect(
            "studios:admin_dashboard_settings",
            studio_slug=studio.slug,
        )

    layout = normalize_admin_dashboard_layout(
        preference.layout
    )

    context = {
        "studio": studio,
        "role": "administrator",
        "settings_section": "admin_dashboard",
        "editor_cards": admin_dashboard_editor_cards(layout),
        "snapshot_metric_options": admin_snapshot_metric_options(layout),
        "snapshot_selected_count": len(layout["snapshot_metrics"]),
        "layout_json": json.dumps(layout),
    }

    context.update(
        quick_links_context(
            layout,
            dashboard_kind="admin",
        )
    )

    return render(
        request,
        "studios/admin_dashboard_settings.html",
        context,
    )
