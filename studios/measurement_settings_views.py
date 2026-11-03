from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .models import Studio, StudioMembership, StudioSettings


def _role(request, studio):
    role = request.session.get("encore_workspace_role")
    if role == StudioMembership.Role.ADMINISTRATOR and (
        request.user.is_superuser
        or request.user.studio_memberships.filter(
            studio=studio, role=role, is_active=True
        ).exists()
    ):
        return role
    return None


@login_required
def measurement_settings(request, studio_slug):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    role = _role(request, studio)
    if role is None:
        return render(request, "dashboard/access_denied.html", {"studio": studio}, status=403)

    settings_obj, _ = StudioSettings.objects.get_or_create(studio=studio)
    if request.method == "POST":
        unit = request.POST.get("measurement_unit", "in")
        months_raw = request.POST.get("remeasurement_interval_months", "6")
        if unit not in {"in", "cm"}:
            unit = "in"
        try:
            months = max(1, min(int(months_raw), 60))
        except (TypeError, ValueError):
            months = 6
        settings_obj.measurement_unit = unit
        settings_obj.remeasurement_interval_months = months
        settings_obj.save(update_fields=["measurement_unit", "remeasurement_interval_months", "updated_at"])
        messages.success(request, "Measurement settings saved.")
        return redirect("studios:measurement_settings", studio_slug=studio.slug)

    return render(request, "studios/measurement_settings.html", {
        "studio": studio,
        "role": role,
        "settings_obj": settings_obj,
        "settings_section": "measurements",
    })
