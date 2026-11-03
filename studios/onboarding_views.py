from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils.html import escape
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
import json

from accounts.dashboard_layouts import (
    class_dashboard_editor_cards,
    default_class_dashboard_layout,
    normalize_class_dashboard_layout,
)
from accounts.dashboard_quick_actions import (
    class_quick_action_choices,
    default_class_quick_actions,
    normalize_class_quick_actions,
)
from accounts.models import DashboardPreference, User
from accounts.teacher_dashboard_layouts import (
    default_teacher_dashboard_layout,
    normalize_teacher_dashboard_layout,
    teacher_dashboard_editor_cards,
    teacher_quick_action_choices,
)
from classes.models import Class, ClassLevel, ClassType, Season
from instructors.models import Instructor
from instructors.activation_services import InstructorActivationError, send_instructor_activation
from communications.email_service import EncoreEmailError, send_email
from studios.models import (
    Studio,
    StudioLocation,
    StudioMembership,
    StudioSettings,
)

from .forms import (
    ClassLevelForm,
    ClassTypeForm,
    SeasonForm,
    StaffInviteForm,
    StudioBrandingForm,
    StudioLocationForm,
    StudioProfileForm,
    PublicWidgetSettingsForm,
    OnboardingMeetingRequestForm,
)


def _admin_workspace(
    request,
    studio,
):
    if request.user.is_superuser:
        return True

    return (
        request.session.get(
            "encore_workspace_role"
        )
        == "administrator"
        and request.session.get(
            "encore_workspace_studio_slug"
        )
        == studio.slug
        and request.user.studio_memberships.filter(
            studio=studio,
            role="administrator",
            is_active=True,
        ).exists()
    )


def _personal_settings_workspace(request, studio):
    role = request.session.get("encore_workspace_role")
    studio_slug = request.session.get("encore_workspace_studio_slug")

    if studio_slug != studio.slug:
        return None

    if request.user.is_superuser and role == "administrator":
        return role

    if role not in {"administrator", "teacher"}:
        return None

    if request.user.studio_memberships.filter(
        studio=studio,
        role=role,
        is_active=True,
    ).exists():
        return role

    return None




def _tour_membership(request, studio):
    if not request.user.is_authenticated:
        return None

    return (
        request.user.studio_memberships
        .filter(
            studio=studio,
            role=StudioMembership.Role.ADMINISTRATOR,
            is_active=True,
        )
        .first()
    )


def _tour_context(request, studio):
    membership = _tour_membership(request, studio)
    if membership is None:
        return {
            "encore_tour_active": False,
            "encore_tour_status": "",
            "encore_tour_step": 0,
        }

    active = membership.onboarding_tour_status in {
        StudioMembership.TourStatus.NOT_STARTED,
        StudioMembership.TourStatus.IN_PROGRESS,
    }

    return {
        "encore_tour_active": active,
        "encore_tour_status": membership.onboarding_tour_status,
        "encore_tour_step": membership.onboarding_tour_step,
    }


def _settings_for_studio(
    studio,
):
    settings_obj, _created = (
        StudioSettings.objects
        .get_or_create(
            studio=studio,
        )
    )

    return settings_obj


def _field_names(model):
    return {
        field.name
        for field
        in model._meta.get_fields()
        if getattr(
            field,
            "concrete",
            False,
        )
    }


@login_required
def onboarding_home(request, studio_slug):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role = _personal_settings_workspace(request, studio)

    if role is None:
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    progress = {}
    percent = None

    if role == "administrator":
        settings_obj = _settings_for_studio(studio)

        progress = {
            "profile": True,
            "branding": bool(
                settings_obj.primary_color
                or settings_obj.logo
            ),
            "locations": StudioLocation.objects.filter(
                studio=studio,
            ).exists(),
            "seasons": Season.objects.filter(
                studio=studio,
            ).exists(),
            "class_types": ClassType.objects.filter(
                studio=studio,
            ).exists(),
            "staff": StudioMembership.objects.filter(
                studio=studio,
                role__in=["administrator", "teacher"],
                is_active=True,
            ).count() > 1,
        }

        completed_count = sum(
            1 for value in progress.values() if value
        )

        percent = round(
            (completed_count / len(progress)) * 100
        )

    preference = DashboardPreference.objects.filter(
        user=request.user,
        studio=studio,
        dashboard_type=DashboardPreference.DashboardType.CLASS,
    ).first()

    teacher_preference = DashboardPreference.objects.filter(
        user=request.user,
        studio=studio,
        dashboard_type=DashboardPreference.DashboardType.TEACHER,
    ).first()

    return render(
        request,
        "studios/onboarding_home.html",
        {
            "studio": studio,
            "role": role,
            "progress": progress,
            "progress_percent": percent,
            "class_dashboard_customized": bool(
                preference and preference.layout
            ),
            "teacher_dashboard_customized": bool(
                teacher_preference
                and teacher_preference.layout
            ),
            "settings_section": "home",
            **_tour_context(request, studio),
        },
    )


@login_required
def class_dashboard_settings(request, studio_slug):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role = _personal_settings_workspace(
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
                (
                    "Class Dashboard layout and "
                    "quick actions reset to default."
                ),
            )

            return redirect(
                "studios:class_dashboard_settings",
                studio_slug=studio.slug,
            )

        raw_layout = request.POST.get(
            "layout_json",
            "",
        )

        try:
            submitted = json.loads(
                raw_layout
            )
        except (
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ):
            submitted = (
                default_class_dashboard_layout()
            )

        normalized_layout = (
            normalize_class_dashboard_layout(
                submitted
            )
        )

        raw_actions = request.POST.get(
            "quick_actions_json",
            "",
        )

        try:
            submitted_actions = json.loads(
                raw_actions
            )
        except (
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ):
            submitted_actions = (
                default_class_quick_actions()
            )

        normalized_layout[
            "quick_actions"
        ] = normalize_class_quick_actions(
            submitted_actions
        )

        preference.layout = normalized_layout

        preference.save(
            update_fields=[
                "layout",
                "updated_at",
            ]
        )

        messages.success(
            request,
            (
                "Class Dashboard layout "
                "and quick actions saved."
            ),
        )

        return redirect(
            "studios:class_dashboard_settings",
            studio_slug=studio.slug,
        )

    layout = normalize_class_dashboard_layout(
        preference.layout
    )

    raw_actions = {}

    if isinstance(
        preference.layout,
        dict,
    ):
        raw_actions = (
            preference.layout.get(
                "quick_actions",
                {},
            )
        )

    quick_actions = (
        normalize_class_quick_actions(
            raw_actions
        )
    )

    return render(
        request,
        "studios/class_dashboard_settings.html",
        {
            "studio": studio,
            "role": role,
            "settings_section": (
                "class_dashboard"
            ),
            "editor_cards": (
                class_dashboard_editor_cards(
                    layout
                )
            ),
            "layout_json": json.dumps(
                layout
            ),
            "quick_actions": (
                class_quick_action_choices(
                    quick_actions
                )
            ),
            "quick_actions_json": json.dumps(
                quick_actions
            ),
        },
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

    role = _personal_settings_workspace(
        request,
        studio,
    )

    if role != "teacher":
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
                (
                    "Teacher Dashboard reset "
                    "to default."
                ),
            )

            return redirect(
                "studios:teacher_dashboard_settings",
                studio_slug=studio.slug,
            )

        raw_layout = request.POST.get(
            "layout_json",
            "",
        )

        try:
            submitted = json.loads(
                raw_layout
            )
        except (
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ):
            submitted = (
                default_teacher_dashboard_layout()
            )

        raw_actions = request.POST.get(
            "quick_actions_json",
            "",
        )

        try:
            submitted_actions = json.loads(
                raw_actions
            )
        except (
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ):
            submitted_actions = {}

        if not isinstance(
            submitted,
            dict,
        ):
            submitted = {}

        submitted[
            "quick_actions"
        ] = submitted_actions

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
            (
                "Teacher Dashboard layout "
                "and quick actions saved."
            ),
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

    return render(
        request,
        "studios/teacher_dashboard_settings.html",
        {
            "studio": studio,
            "role": role,
            "settings_section": (
                "teacher_dashboard"
            ),
            "editor_cards": (
                teacher_dashboard_editor_cards(
                    layout
                )
            ),
            "layout_json": json.dumps(
                layout
            ),
            "quick_actions": (
                teacher_quick_action_choices(
                    layout
                )
            ),
            "quick_actions_json": json.dumps(
                layout[
                    "quick_actions"
                ]
            ),
        },
    )


@login_required
def studio_profile(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if not _admin_workspace(
        request,
        studio,
    ):
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    form = StudioProfileForm(
        request.POST or None,
        instance=studio,
    )

    if (
        request.method == "POST"
        and form.is_valid()
    ):
        form.save()

        messages.success(
            request,
            "Studio profile updated.",
        )

        return redirect(
            "studios:onboarding_home",
            studio_slug=studio.slug,
        )

    return render(
        request,
        "studios/settings_form.html",
        {
            "studio": studio,
            "role": "administrator",
            "form": form,
            "page_title": "Studio Profile",
            "page_intro": (
                "Configure the basic identity for this studio."
            ),
            "settings_section": "profile",
        },
    )


@login_required
def studio_branding(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if not _admin_workspace(
        request,
        studio,
    ):
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    settings_obj = _settings_for_studio(
        studio
    )

    form = StudioBrandingForm(
        request.POST or None,
        request.FILES or None,
        instance=settings_obj,
    )

    if (
        request.method == "POST"
        and form.is_valid()
    ):
        form.save()

        messages.success(
            request,
            "Branding and registration settings updated.",
        )

        return redirect(
            "studios:onboarding_home",
            studio_slug=studio.slug,
        )

    return render(
        request,
        "studios/settings_form.html",
        {
            "studio": studio,
            "role": "administrator",
            "form": form,
            "page_title": "Branding & Registration",
            "page_intro": (
                "Control how this studio appears inside Encore "
                "and on its public registration pages."
            ),
            "settings_section": "branding",
        },
    )


def _public_absolute_uri(request, path):
    """Build public/widget URLs correctly through production proxies and local Docker."""
    configured = str(getattr(settings, "ENCORE_PUBLIC_BASE_URL", "") or "").strip().rstrip("/")
    if configured:
        return f"{configured}{path}"

    url = request.build_absolute_uri(path)
    if getattr(settings, "DEBUG", False):
        from urllib.parse import urlsplit, urlunsplit

        parsed = urlsplit(url)
        if parsed.hostname in {"127.0.0.1", "localhost"} and parsed.port is None:
            host = parsed.hostname + ":8000"
            url = urlunsplit((parsed.scheme or "http", host, parsed.path, parsed.query, parsed.fragment))
    return url


@login_required
def widget_settings(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if not _admin_workspace(
        request,
        studio,
    ):
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    settings_obj = _settings_for_studio(
        studio
    )

    form = PublicWidgetSettingsForm(
        request.POST or None,
        studio=studio,
        settings_obj=settings_obj,
    )

    if (
        request.method == "POST"
        and form.is_valid()
    ):
        form.save()

        messages.success(
            request,
            "Widget and public page settings updated.",
        )

        return redirect(
            "studios:widget_settings",
            studio_slug=studio.slug,
        )

    base_context = {
        "studio": studio,
        "role": "administrator",
        "form": form,
        "settings_section": "widgets",
        "settings_obj": settings_obj,
        "calendar_public_url": _public_absolute_uri(
            request,
            reverse(
                "registration_portal:public_calendar",
                kwargs={"studio_slug": studio.slug},
            )
        ),
        "calendar_embed_url": _public_absolute_uri(
            request,
            reverse(
                "registration_portal:embedded_calendar",
                kwargs={"studio_slug": studio.slug},
            )
        ),
        "classes_public_url": _public_absolute_uri(
            request,
            reverse(
                "registration_portal:public_class_catalog",
                kwargs={"studio_slug": studio.slug},
            )
        ),
        "classes_embed_url": _public_absolute_uri(
            request,
            reverse(
                "registration_portal:embedded_class_catalog",
                kwargs={"studio_slug": studio.slug},
            )
        ),
        "registration_public_url": _public_absolute_uri(
            request,
            reverse(
                "registration_portal:public_registration_home",
                kwargs={"studio_slug": studio.slug},
            )
        ),
        "registration_embed_url": _public_absolute_uri(
            request,
            reverse(
                "registration_portal:embedded_registration_home",
                kwargs={"studio_slug": studio.slug},
            )
        ),
    }

    return render(
        request,
        "studios/widget_settings.html",
        base_context,
    )


@login_required
def location_list(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if not _admin_workspace(
        request,
        studio,
    ):
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    return render(
        request,
        "studios/location_list.html",
        {
            "studio": studio,
            "role": "administrator",
            "locations": StudioLocation.objects.filter(
                studio=studio,
            ),
        },
    )


@login_required
def location_add(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if not _admin_workspace(
        request,
        studio,
    ):
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    form = StudioLocationForm(
        request.POST or None
    )

    if (
        request.method == "POST"
        and form.is_valid()
    ):
        location = form.save(
            commit=False
        )

        location.studio = studio
        location.full_clean()
        location.save()

        messages.success(
            request,
            "Studio location added.",
        )

        return redirect(
            "studios:location_list",
            studio_slug=studio.slug,
        )

    return render(
        request,
        "studios/settings_form.html",
        {
            "studio": studio,
            "role": "administrator",
            "form": form,
            "page_title": "Add Studio Location",
            "page_intro": (
                "Add a building, room, or teaching location."
            ),
        },
    )


@login_required
def season_list(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if not _admin_workspace(
        request,
        studio,
    ):
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    return render(
        request,
        "studios/season_list.html",
        {
            "studio": studio,
            "role": "administrator",
            "seasons": Season.objects.filter(
                studio=studio,
            ).order_by(
                "-start_date",
            ),
            "settings_section": "seasons",
        },
    )


@login_required
def season_add(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if not _admin_workspace(
        request,
        studio,
    ):
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    form = SeasonForm(
        request.POST or None
    )

    if (
        request.method == "POST"
        and form.is_valid()
    ):
        season = form.save(
            commit=False
        )

        season.studio = studio
        season.full_clean()
        season.save()

        messages.success(
            request,
            "Season added.",
        )

        return redirect(
            "studios:season_list",
            studio_slug=studio.slug,
        )

    return render(
        request,
        "studios/settings_form.html",
        {
            "studio": studio,
            "role": "administrator",
            "form": form,
            "page_title": "Add Season",
            "page_intro": (
                "Create a term or performance season."
            ),
            "settings_section": "seasons",
        },
    )


@login_required
def class_type_list(request, studio_slug):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if not _admin_workspace(request, studio):
        return render(request, "dashboard/access_denied.html", {"studio": studio}, status=403)

    query = (request.GET.get("q") or "").strip()[:120]
    status = (request.GET.get("status") or "active").lower()
    if status not in {"active", "inactive", "all"}:
        status = "active"

    if request.method == "POST":
        selected = request.POST.getlist("selected_types")
        action = request.POST.get("bulk_action")
        selected_ids = {int(value) for value in selected if value.isdecimal() and len(value) <= 18}
        if action not in {"activate", "deactivate"}:
            messages.error(request, "Choose a valid bulk action.")
        elif not selected_ids:
            messages.error(request, "Select at least one class type.")
        else:
            target_active = action == "activate"
            changed = ClassType.objects.filter(
                studio=studio, id__in=selected_ids
            ).exclude(is_active=target_active).update(is_active=target_active)
            messages.success(request, f"Updated {changed} class type(s) to {'Active' if target_active else 'Inactive'}.")
        params = []
        from urllib.parse import urlencode
        if query:
            params.append(("q", query))
        params.append(("status", status))
        url = reverse("studios:class_type_list", kwargs={"studio_slug": studio.slug})
        return redirect(f"{url}?{urlencode(params)}")

    types = ClassType.objects.filter(studio=studio)
    active_count = types.filter(is_active=True).count()
    inactive_count = types.filter(is_active=False).count()
    if query:
        types = types.filter(name__icontains=query)
    if status != "all":
        types = types.filter(is_active=(status == "active"))

    return render(request, "studios/class_type_list.html", {
        "studio": studio,
        "role": "administrator",
        "class_types": types.order_by("name", "pk"),
        "settings_section": "class_types",
        "filter_query": query,
        "filter_status": status,
        "active_count": active_count,
        "inactive_count": inactive_count,
    })


@login_required
def class_type_add(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if not _admin_workspace(
        request,
        studio,
    ):
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    form = ClassTypeForm(
        request.POST or None
    )

    if (
        request.method == "POST"
        and form.is_valid()
    ):
        class_type = form.save(
            commit=False
        )

        class_type.studio = studio
        class_type.full_clean()
        class_type.save()

        messages.success(
            request,
            "Class type added.",
        )

        return redirect(
            "studios:class_type_list",
            studio_slug=studio.slug,
        )

    return render(
        request,
        "studios/settings_form.html",
        {
            "studio": studio,
            "role": "administrator",
            "form": form,
            "page_title": "Add Class Type",
            "page_intro": (
                "Create categories such as Ballet, Jazz, Tap, "
                "Hip Hop, Competition, or Adult."
            ),
            "settings_section": "class_types",
        },
    )


@login_required
def class_level_list(request, studio_slug):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if not _admin_workspace(request, studio):
        return render(request, "dashboard/access_denied.html", {"studio": studio}, status=403)

    return render(
        request,
        "studios/class_level_list.html",
        {
            "studio": studio,
            "role": "administrator",
            "class_levels": ClassLevel.objects.filter(studio=studio).order_by("number", "name"),
            "settings_section": "class_levels",
        },
    )


@login_required
def class_level_add(request, studio_slug):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if not _admin_workspace(request, studio):
        return render(request, "dashboard/access_denied.html", {"studio": studio}, status=403)

    form = ClassLevelForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.studio = studio
        obj.full_clean()
        obj.save()
        messages.success(request, f"Level {obj.number} — {obj.name} added.")
        return redirect("studios:class_level_list", studio_slug=studio.slug)

    return render(request, "studios/settings_form.html", {
        "studio": studio, "role": "administrator", "form": form,
        "page_title": "Add Class Level",
        "page_intro": "Define a reusable experience level and the shorthand Encore should recognize during onboarding.",
        "settings_section": "class_levels",
        "cancel_url_name": "studios:class_level_list",
    })


@login_required
def class_level_edit(request, studio_slug, level_id):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if not _admin_workspace(request, studio):
        return render(request, "dashboard/access_denied.html", {"studio": studio}, status=403)

    obj = get_object_or_404(ClassLevel, pk=level_id, studio=studio)
    form = ClassLevelForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.studio = studio
        obj.full_clean()
        obj.save()
        messages.success(request, "Class level updated.")
        return redirect("studios:class_level_list", studio_slug=studio.slug)

    return render(request, "studios/settings_form.html", {
        "studio": studio, "role": "administrator", "form": form,
        "page_title": "Edit Class Level",
        "page_intro": "Update the display name and shorthand used for this experience level.",
        "settings_section": "class_levels",
        "cancel_url_name": "studios:class_level_list",
    })


@login_required
def class_level_delete(request, studio_slug, level_id):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if not _admin_workspace(request, studio):
        return render(request, "dashboard/access_denied.html", {"studio": studio}, status=403)

    obj = get_object_or_404(ClassLevel, pk=level_id, studio=studio)
    if request.method != "POST":
        return redirect("studios:class_level_list", studio_slug=studio.slug)
    if Class.objects.filter(studio=studio, level=obj).exists():
        messages.error(request, "This level is assigned to classes. Reassign those classes first, or mark the level inactive.")
    else:
        label = str(obj)
        obj.delete()
        messages.success(request, f"{label} was removed.")
    return redirect("studios:class_level_list", studio_slug=studio.slug)


@login_required
def staff_invite(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if not _admin_workspace(request, studio):
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    form = StaffInviteForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]
        role = form.cleaned_data["role"]
        first_name = form.cleaned_data["first_name"]
        last_name = form.cleaned_data["last_name"]

        if role == "teacher":
            instructor = (
                Instructor.objects
                .filter(studio=studio, email__iexact=email)
                .first()
            )

            if instructor is None:
                instructor = Instructor.objects.create(
                    studio=studio,
                    first_name=first_name,
                    last_name=last_name,
                    email=email,
                    is_active=True,
                )
            else:
                instructor.first_name = first_name
                instructor.last_name = last_name
                instructor.email = email
                instructor.is_active = True
                instructor.save(
                    update_fields=[
                        "first_name",
                        "last_name",
                        "email",
                        "is_active",
                        "updated_at",
                    ]
                )

            if instructor.claimed_at and instructor.user_id:
                messages.info(
                    request,
                    f"{first_name} {last_name} already has an active Encore teacher account.",
                )
                return redirect(
                    "studios:onboarding_home",
                    studio_slug=studio.slug,
                )

            try:
                send_instructor_activation(
                    request=request,
                    instructor=instructor,
                )
            except InstructorActivationError as exc:
                messages.warning(
                    request,
                    f"{first_name} {last_name} was added, but the activation email could not be sent: {exc}",
                )
            else:
                messages.success(
                    request,
                    f"{first_name} {last_name} was added as a teacher and sent a secure account activation email.",
                )

            return redirect(
                "studios:onboarding_home",
                studio_slug=studio.slug,
            )

        # Administrators keep the existing immediate-access flow. Teachers use
        # the secure claim flow above and create/connect their own login.
        user = User.objects.filter(email__iexact=email).first()
        created_password = None

        if user is None:
            created_password = User.objects.make_random_password(length=16)
            user = User.objects.create_user(
                username=email,
                email=email,
                password=created_password,
                first_name=first_name,
                last_name=last_name,
            )

        membership, _created = StudioMembership.objects.get_or_create(
            user=user,
            studio=studio,
            role=role,
            defaults={"is_active": True},
        )
        if not membership.is_active:
            membership.is_active = True
            membership.save(update_fields=["is_active"])

        body_lines = [
            f"You have been added to {studio.name} in Encore.",
            "",
            "Sign in at:",
            request.build_absolute_uri("/accounts/login/"),
        ]
        if created_password:
            body_lines += [
                "",
                f"Temporary password: {created_password}",
                "",
                "Please change your password after signing in.",
            ]

        send_mail(
            subject=f"Encore access for {studio.name}",
            message="\n".join(body_lines),
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            recipient_list=[email],
            fail_silently=True,
        )

        messages.success(
            request,
            f"{first_name} {last_name} was added as {role}.",
        )
        return redirect(
            "studios:onboarding_home",
            studio_slug=studio.slug,
        )

    return render(
        request,
        "studios/settings_form.html",
        {
            "studio": studio,
            "role": "administrator",
            "form": form,
            "page_title": "Invite Staff",
            "page_intro": (
                "Add an Administrator or Teacher to this studio. "
                "Teachers receive a secure activation link and create their own login."
            ),
            "settings_section": "staff",
        },
    )


@login_required
def season_edit(request, studio_slug, season_id):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if not _admin_workspace(request, studio):
        return render(request, "dashboard/access_denied.html", {"studio": studio}, status=403)

    season = get_object_or_404(Season, pk=season_id, studio=studio)
    form = SeasonForm(request.POST or None, instance=season)

    if request.method == "POST" and form.is_valid():
        season = form.save(commit=False)
        season.studio = studio
        season.full_clean()
        season.save()
        messages.success(request, "Season updated.")
        return redirect("studios:season_list", studio_slug=studio.slug)

    return render(
        request,
        "studios/settings_form.html",
        {
            "studio": studio,
            "role": "administrator",
            "form": form,
            "page_title": "Edit Season",
            "page_intro": "Update this season's name, dates, and availability.",
            "settings_section": "seasons",
            "cancel_url_name": "studios:season_list",
        },
    )


@login_required
def season_delete(request, studio_slug, season_id):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if not _admin_workspace(request, studio):
        return render(request, "dashboard/access_denied.html", {"studio": studio}, status=403)

    season = get_object_or_404(Season, pk=season_id, studio=studio)
    if request.method != "POST":
        return redirect("studios:season_list", studio_slug=studio.slug)

    if Class.objects.filter(studio=studio, season=season).exists():
        messages.error(
            request,
            "This season still has classes attached to it. Move or remove those classes first, "
            "or edit the season and mark it inactive if that option is available.",
        )
    else:
        name = season.name
        season.delete()
        messages.success(request, f"{name} was removed.")

    return redirect("studios:season_list", studio_slug=studio.slug)


@login_required
def class_type_edit(request, studio_slug, class_type_id):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if not _admin_workspace(request, studio):
        return render(request, "dashboard/access_denied.html", {"studio": studio}, status=403)

    class_type = get_object_or_404(ClassType, pk=class_type_id, studio=studio)
    form = ClassTypeForm(request.POST or None, instance=class_type)

    if request.method == "POST" and form.is_valid():
        class_type = form.save(commit=False)
        class_type.studio = studio
        class_type.full_clean()
        class_type.save()
        messages.success(request, "Class type updated.")
        return redirect("studios:class_type_list", studio_slug=studio.slug)

    return render(
        request,
        "studios/settings_form.html",
        {
            "studio": studio,
            "role": "administrator",
            "form": form,
            "page_title": "Edit Class Type",
            "page_intro": "Update this class category.",
            "settings_section": "class_types",
            "cancel_url_name": "studios:class_type_list",
        },
    )


@login_required
def class_type_delete(request, studio_slug, class_type_id):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if not _admin_workspace(request, studio):
        return render(request, "dashboard/access_denied.html", {"studio": studio}, status=403)

    class_type = get_object_or_404(ClassType, pk=class_type_id, studio=studio)
    if request.method != "POST":
        return redirect("studios:class_type_list", studio_slug=studio.slug)

    if Class.objects.filter(studio=studio, class_type=class_type).exists():
        messages.error(
            request,
            "This class type is still assigned to one or more classes. Change those classes first, "
            "or edit the class type and mark it inactive if that option is available.",
        )
    else:
        name = class_type.name
        class_type.delete()
        messages.success(request, f"{name} was removed.")

    return redirect("studios:class_type_list", studio_slug=studio.slug)


@login_required
@require_POST
def onboarding_tour_update(request, studio_slug):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )
    membership = _tour_membership(request, studio)
    if membership is None:
        return JsonResponse({"ok": False, "error": "Access denied."}, status=403)

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except (TypeError, ValueError, json.JSONDecodeError, UnicodeDecodeError):
        payload = {}

    action = str(payload.get("action") or "progress").strip().lower()

    try:
        step = int(payload.get("step", membership.onboarding_tour_step))
    except (TypeError, ValueError):
        step = membership.onboarding_tour_step

    step = max(0, min(step, 50))

    if action == "skip":
        membership.onboarding_tour_status = StudioMembership.TourStatus.SKIPPED
    elif action == "complete":
        membership.onboarding_tour_status = StudioMembership.TourStatus.COMPLETED
    else:
        membership.onboarding_tour_status = StudioMembership.TourStatus.IN_PROGRESS
        membership.onboarding_tour_step = step

    membership.save(
        update_fields=[
            "onboarding_tour_status",
            "onboarding_tour_step",
        ]
    )

    return JsonResponse(
        {
            "ok": True,
            "status": membership.onboarding_tour_status,
            "step": membership.onboarding_tour_step,
        }
    )


@login_required
def onboarding_meeting_request(request, studio_slug):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if not _admin_workspace(request, studio):
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    initial = {
        "name": request.user.get_full_name() or request.user.username,
        "email": request.user.email,
        "phone": studio.phone,
        "timezone": studio.timezone or settings.TIME_ZONE,
    }
    form = OnboardingMeetingRequestForm(
        request.POST or None,
        initial=initial if request.method != "POST" else None,
    )
    submitted = False

    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        migration_labels = [
            dict(form.MIGRATION_CHOICES).get(value, value)
            for value in data.get("migration_help", [])
        ]
        platform_label = dict(form.CURRENT_PLATFORM_CHOICES).get(
            data["current_platform"],
            data["current_platform"],
        )
        student_label = dict(form.STUDENT_COUNT_CHOICES).get(
            data["student_count"],
            data["student_count"],
        )

        subject = f"Encore onboarding meeting request — {studio.name}"
        text_body = "\n".join(
            [
                "New Encore onboarding meeting request",
                "",
                f"Studio: {studio.name}",
                f"Studio ID: {studio.pk}",
                f"Name: {data['name']}",
                f"Email: {data['email']}",
                f"Phone: {data.get('phone') or 'Not provided'}",
                f"Current software: {platform_label}",
                f"Approx. student count: {student_label}",
                f"Preferred date: {data['preferred_date'].isoformat()}",
                f"Preferred time: {data['preferred_time'].strftime('%I:%M %p')}",
                f"Time zone: {data['timezone']}",
                "Help requested: " + (", ".join(migration_labels) or "Not specified"),
                "",
                "Notes:",
                data.get("notes") or "None",
            ]
        )
        html_body = f"""
            <div style="font-family:Arial,sans-serif;line-height:1.55;color:#10153f;">
                <h2>New Encore onboarding meeting request</h2>
                <p><strong>Studio:</strong> {escape(studio.name)}</p>
                <p><strong>Studio ID:</strong> {studio.pk}</p>
                <p><strong>Name:</strong> {escape(data['name'])}</p>
                <p><strong>Email:</strong> {escape(data['email'])}</p>
                <p><strong>Phone:</strong> {escape(data.get('phone') or 'Not provided')}</p>
                <p><strong>Current software:</strong> {escape(platform_label)}</p>
                <p><strong>Approx. student count:</strong> {escape(student_label)}</p>
                <p><strong>Preferred date:</strong> {escape(data['preferred_date'].strftime('%B %d, %Y'))}</p>
                <p><strong>Preferred time:</strong> {escape(data['preferred_time'].strftime('%I:%M %p'))}</p>
                <p><strong>Time zone:</strong> {escape(data['timezone'])}</p>
                <p><strong>Help requested:</strong> {escape(', '.join(migration_labels) or 'Not specified')}</p>
                <p><strong>Notes:</strong><br>{escape(data.get('notes') or 'None').replace(chr(10), '<br>')}</p>
            </div>
        """

        try:
            send_email(
                to=[settings.ENCORE_ONBOARDING_EMAIL],
                subject=subject,
                html_body=html_body,
                text_body=text_body,
                reply_to=[data["email"]],
                tags={
                    "message_type": "onboarding_request",
                    "studio_id": studio.pk,
                },
            )
        except EncoreEmailError as exc:
            messages.error(
                request,
                "We could not send your onboarding request right now. Please try again.",
            )
            if settings.DEBUG:
                messages.error(request, str(exc))
        else:
            submitted = True
            form = OnboardingMeetingRequestForm(initial=initial)

    return render(
        request,
        "studios/onboarding_meeting_request.html",
        {
            "studio": studio,
            "role": "administrator",
            "settings_section": "data_transfer",
            "form": form,
            "submitted": submitted,
        },
    )
