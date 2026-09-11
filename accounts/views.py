from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .forms import EncoreLoginForm, StudioOwnerRegistrationForm


ROLE_LABELS = {
    "administrator": "Administrator",
    "teacher": "Teacher",
    "family": "Family / Guardian",
    "student": "Student",
}

ROLE_DESCRIPTIONS = {
    "administrator": "Manage the studio, classes, people, enrollment, and operations.",
    "teacher": "Access classes, rosters, attendance, schedules, and teaching tools.",
    "family": "Manage your dancers, schedules, attendance, registration, and account.",
    "student": "View your classes, calendar, attendance, and student resources.",
}


def _membership_destination(membership):
    role = membership.role
    studio_slug = membership.studio.slug

    if role == "administrator":
        return reverse(
            "dashboard:admin_dashboard",
            kwargs={"studio_slug": studio_slug},
        )

    if role == "teacher":
        return reverse(
            "dashboard:teacher_dashboard",
            kwargs={"studio_slug": studio_slug},
        )

    if role == "family":
        return reverse(
            "dashboard:family_dashboard",
            kwargs={"studio_slug": studio_slug},
        )

    if role == "student":
        return reverse(
            "dashboard:student_dashboard",
            kwargs={"studio_slug": studio_slug},
        )

    raise Http404


def _active_memberships(user):
    return (
        user.studio_memberships
        .filter(
            is_active=True,
            studio__is_active=True,
        )
        .select_related("studio")
        .order_by("studio__name", "role")
    )


def _set_workspace_session(request, membership):
    request.session["encore_workspace_membership_id"] = membership.pk
    request.session["encore_workspace_studio_slug"] = membership.studio.slug
    request.session["encore_workspace_role"] = membership.role


def _post_login_destination(request, user):
    memberships = list(_active_memberships(user))

    if user.is_superuser:
        admin_membership = next(
            (
                membership
                for membership in memberships
                if membership.role == "administrator"
            ),
            None,
        )

        if admin_membership:
            _set_workspace_session(request, admin_membership)
            return _membership_destination(admin_membership)

        if memberships:
            _set_workspace_session(request, memberships[0])
            return _membership_destination(memberships[0])

        return "/admin/"

    if not memberships:
        return reverse("accounts:no_studio_access")

    if len(memberships) == 1:
        membership = memberships[0]
        _set_workspace_session(request, membership)
        return _membership_destination(membership)

    return reverse("accounts:workspace_selector")


def login_view(request):
    if request.user.is_authenticated:
        return redirect(
            _post_login_destination(
                request,
                request.user,
            )
        )

    form = EncoreLoginForm(
        request.POST or None,
        request=request,
    )

    if request.method == "POST" and form.is_valid():
        user = form.get_user()

        login(
            request,
            user,
        )

        next_url = request.GET.get("next")

        if next_url and next_url.startswith("/"):
            return redirect(next_url)

        return redirect(
            _post_login_destination(
                request,
                user,
            )
        )

    return render(
        request,
        "accounts/login.html",
        {
            "form": form,
        },
    )


@login_required
def workspace_selector(request):
    memberships = list(
        _active_memberships(request.user)
    )

    if not memberships and request.user.is_superuser:
        return redirect("/admin/")

    if not memberships:
        return redirect("accounts:no_studio_access")

    if len(memberships) == 1:
        membership = memberships[0]
        _set_workspace_session(request, membership)
        return redirect(_membership_destination(membership))

    workspace_cards = [
        {
            "membership": membership,
            "studio": membership.studio,
            "role": membership.role,
            "role_label": ROLE_LABELS.get(
                membership.role,
                membership.get_role_display(),
            ),
            "description": ROLE_DESCRIPTIONS.get(
                membership.role,
                "",
            ),
            "is_current": (
                request.session.get(
                    "encore_workspace_membership_id"
                )
                == membership.pk
            ),
        }
        for membership in memberships
    ]

    return render(
        request,
        "accounts/workspace_selector.html",
        {
            "workspace_cards": workspace_cards,
        },
    )


@login_required
def select_workspace(request, membership_id):
    membership = (
        _active_memberships(request.user)
        .filter(pk=membership_id)
        .first()
    )

    if membership is None:
        raise Http404

    _set_workspace_session(
        request,
        membership,
    )

    return redirect(
        _membership_destination(membership)
    )



@login_required
def profile_view(request):
    user = request.user

    studio_slug = request.session.get(
        "encore_workspace_studio_slug"
    )

    role = request.session.get(
        "encore_workspace_role"
    )

    if not studio_slug or not role:
        return redirect(
            "accounts:workspace_selector"
        )

    current_membership = (
        _active_memberships(user)
        .filter(
            studio__slug=studio_slug,
            role=role,
        )
        .first()
    )

    if current_membership is None:
        return redirect(
            "accounts:workspace_selector"
        )

    studio = current_membership.studio

    if request.method == "POST":
        user.first_name = request.POST.get(
            "first_name",
            "",
        ).strip()

        user.last_name = request.POST.get(
            "last_name",
            "",
        ).strip()

        user.save(
            update_fields=[
                "first_name",
                "last_name",
            ]
        )

        messages.success(
            request,
            "Profile updated.",
        )

        return redirect(
            "accounts:profile"
        )

    memberships = list(
        _active_memberships(user)
    )

    return render(
        request,
        "accounts/profile.html",
        {
            "memberships": memberships,
            "studio": studio,
            "role": role,
        },
    )

def logout_view(request):
    logout(request)
    return redirect("accounts:login")


def no_studio_access(request):
    return render(
        request,
        "accounts/no_studio_access.html",
        status=403,
    )


def register_studio(request):
    if request.user.is_authenticated:
        return redirect(
            _post_login_destination(
                request,
                request.user,
            )
        )

    from billing.subscription_services import (
        create_checkout_session,
        create_signup_intent,
        price_catalog_rows,
    )

    form = StudioOwnerRegistrationForm(
        request.POST or None,
    )

    if (
        request.method == "POST"
        and form.is_valid()
    ):
        intent = create_signup_intent(
            form.cleaned_data
        )

        try:
            checkout = create_checkout_session(
                request,
                intent,
            )
        except Exception as exc:
            messages.error(
                request,
                (
                    "Encore could not start secure checkout. "
                    "Please try again."
                ),
            )

            if settings.DEBUG:
                messages.error(
                    request,
                    str(exc),
                )
        else:
            return redirect(
                checkout.url
            )

    return render(
        request,
        "accounts/register_studio.html",
        {
            "form": form,
            "pricing_rows": price_catalog_rows(),
            "drawing_board_price": 39,
        },
    )


def registration_success(request):
    from billing.models import (
        StudioSignupIntent,
    )
    from billing.subscription_services import (
        finalize_paid_signup,
    )

    session_id = request.GET.get(
        "session_id",
        "",
    ).strip()

    if not session_id:
        return redirect(
            "accounts:register"
        )

    intent = get_object_or_404(
        StudioSignupIntent,
        stripe_checkout_session_id=session_id,
    )

    try:
        studio = finalize_paid_signup(
            intent
        )
    except Exception as exc:
        return render(
            request,
            "accounts/registration_pending.html",
            {
                "error": (
                    str(exc)
                    if settings.DEBUG
                    else ""
                ),
            },
        )

    User = get_user_model()

    user = User.objects.get(
        email=intent.owner_email,
    )

    login(
        request,
        user,
    )

    membership = (
        user.studio_memberships
        .get(
            studio=studio,
            role="administrator",
            is_active=True,
        )
    )

    _set_workspace_session(
        request,
        membership,
    )

    messages.success(
        request,
        (
            "Welcome to Encore! Your subscription is active. "
            "Let's set up your studio."
        ),
    )

    return redirect(
        "studios:onboarding_home",
        studio_slug=studio.slug,
    )
