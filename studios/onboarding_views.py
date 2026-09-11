from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
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
from classes.models import Class, ClassType, Season
from instructors.models import Instructor
from studios.models import (
    Studio,
    StudioLocation,
    StudioMembership,
    StudioSettings,
)

from .forms import (
    ClassTypeForm,
    SeasonForm,
    StaffInviteForm,
    StudioBrandingForm,
    StudioLocationForm,
    StudioProfileForm,
    PublicWidgetSettingsForm,
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
        "calendar_public_url": request.build_absolute_uri(
            reverse(
                "registration_portal:public_calendar",
                kwargs={"studio_slug": studio.slug},
            )
        ),
        "calendar_embed_url": request.build_absolute_uri(
            reverse(
                "registration_portal:embedded_calendar",
                kwargs={"studio_slug": studio.slug},
            )
        ),
        "classes_public_url": request.build_absolute_uri(
            reverse(
                "registration_portal:public_class_catalog",
                kwargs={"studio_slug": studio.slug},
            )
        ),
        "classes_embed_url": request.build_absolute_uri(
            reverse(
                "registration_portal:embedded_class_catalog",
                kwargs={"studio_slug": studio.slug},
            )
        ),
        "registration_public_url": request.build_absolute_uri(
            reverse(
                "registration_portal:public_registration_home",
                kwargs={"studio_slug": studio.slug},
            )
        ),
        "registration_embed_url": request.build_absolute_uri(
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
def class_type_list(
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
        "studios/class_type_list.html",
        {
            "studio": studio,
            "role": "administrator",
            "class_types": ClassType.objects.filter(
                studio=studio,
            ).order_by("name"),
            "settings_section": "class_types",
        },
    )


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
def staff_invite(
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

    form = StaffInviteForm(
        request.POST or None
    )

    if (
        request.method == "POST"
        and form.is_valid()
    ):
        email = form.cleaned_data[
            "email"
        ]

        role = form.cleaned_data[
            "role"
        ]

        user = User.objects.filter(
            email__iexact=email,
        ).first()

        created_password = None

        if user is None:
            created_password = (
                User.objects
                .make_random_password(
                    length=16,
                )
            )

            user = User.objects.create_user(
                username=email,
                email=email,
                password=created_password,
                first_name=form.cleaned_data[
                    "first_name"
                ],
                last_name=form.cleaned_data[
                    "last_name"
                ],
            )

        membership, _created = (
            StudioMembership.objects
            .get_or_create(
                user=user,
                studio=studio,
                role=role,
                defaults={
                    "is_active": True,
                },
            )
        )

        if not membership.is_active:
            membership.is_active = True
            membership.save(
                update_fields=[
                    "is_active",
                ]
            )

        if role == "teacher":
            instructor_fields = _field_names(
                Instructor
            )

            payload = {
                "studio": studio,
                "user": user,
            }

            for field_name, value in {
                "first_name": form.cleaned_data[
                    "first_name"
                ],
                "last_name": form.cleaned_data[
                    "last_name"
                ],
                "email": email,
                "is_active": True,
            }.items():
                if field_name in instructor_fields:
                    payload[
                        field_name
                    ] = value

            Instructor.objects.get_or_create(
                studio=studio,
                user=user,
                defaults=payload,
            )

        body_lines = [
            (
                f"You have been added to "
                f"{studio.name} in Encore."
            ),
            "",
            "Sign in at:",
            request.build_absolute_uri(
                "/accounts/login/"
            ),
        ]

        if created_password:
            body_lines += [
                "",
                (
                    "Temporary password: "
                    f"{created_password}"
                ),
                "",
                (
                    "Please change your password "
                    "after signing in."
                ),
            ]

        send_mail(
            subject=(
                f"Encore access for "
                f"{studio.name}"
            ),
            message="\n".join(
                body_lines
            ),
            from_email=getattr(
                settings,
                "DEFAULT_FROM_EMAIL",
                None,
            ),
            recipient_list=[
                email,
            ],
            fail_silently=True,
        )

        messages.success(
            request,
            (
                f"{form.cleaned_data['first_name']} "
                f"{form.cleaned_data['last_name']} "
                f"was added as {role}."
            ),
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
                "Add an Administrator or Teacher to this studio."
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
