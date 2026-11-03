from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .forms import EncoreLoginForm, StudioOwnerRegistrationForm
from families.models import Guardian
from dashboard.parent_portal import parent_portal_context


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
    guardian = None

    if role == "family":
        guardian = (
            Guardian.objects
            .filter(
                family__studio=studio,
                user=user,
                is_active=True,
            )
            .select_related("family")
            .order_by("-is_primary", "pk")
            .first()
        )

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

        if guardian is not None:
            guardian.first_name = user.first_name
            guardian.last_name = user.last_name
            guardian.phone = request.POST.get(
                "phone",
                guardian.phone,
            ).strip()
            guardian.save(
                update_fields=[
                    "first_name",
                    "last_name",
                    "phone",
                    "updated_at",
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

    context = {
        "memberships": memberships,
        "studio": studio,
        "role": role,
    }

    template_name = "accounts/profile.html"

    if role == "family" and guardian is not None:
        context.update(
            parent_portal_context(
                request,
                studio,
                section="account",
            )
        )
        context["profile_guardian"] = guardian
        template_name = "accounts/parent_profile.html"

    return render(
        request,
        template_name,
        context,
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


def _masked_email(value):
    value = (value or "").strip()
    if "@" not in value:
        return value
    local, domain = value.split("@", 1)
    if len(local) <= 2:
        masked = local[:1] + "•"
    else:
        masked = local[:1] + ("•" * min(6, len(local) - 2)) + local[-1:]
    return f"{masked}@{domain}"


def registration_success(request):
    from billing.models import StudioSignupIntent
    from billing.subscription_services import finalize_paid_signup
    from accounts.registration_services import (
        ensure_signup_communications,
        signup_receipt_context,
    )

    session_id = request.GET.get("session_id", "").strip()
    if not session_id:
        return redirect("accounts:register")

    intent = get_object_or_404(
        StudioSignupIntent,
        stripe_checkout_session_id=session_id,
    )

    try:
        studio = finalize_paid_signup(intent)
        intent.refresh_from_db()
        ensure_signup_communications(intent)
        receipt = signup_receipt_context(intent)
    except Exception as exc:
        return render(
            request,
            "accounts/registration_pending.html",
            {
                "error": str(exc) if settings.DEBUG else "",
            },
        )

    user = get_user_model().objects.get(email=intent.owner_email)

    return render(
        request,
        "accounts/registration_complete.html",
        {
            "studio": studio,
            "intent": intent,
            "masked_email": _masked_email(intent.owner_email),
            "receipt": receipt,
            "session_id": session_id,
            "verification_sent": bool(user.email_verification_sent_at),
        },
    )


def resend_registration_verification(request):
    from billing.models import StudioSignupIntent
    from accounts.registration_services import send_verification_email

    if request.method != "POST":
        return redirect("accounts:register")

    session_id = request.POST.get("session_id", "").strip()
    intent = get_object_or_404(
        StudioSignupIntent,
        stripe_checkout_session_id=session_id,
        status=StudioSignupIntent.Status.PAID,
    )

    try:
        sent = send_verification_email(intent, force=True)
    except ValueError as exc:
        messages.info(request, str(exc))
    except Exception:
        messages.error(
            request,
            "Encore could not resend the verification email right now. Please try again in a moment.",
        )
    else:
        if sent:
            messages.success(
                request,
                "A new verification link was sent to your email.",
            )

    return redirect(
        f"{reverse('accounts:registration_success')}?session_id={session_id}"
    )


def verify_registration_email(request, token):
    from django.utils import timezone
    from accounts.registration_services import verification_is_expired
    from billing.models import StudioSignupIntent

    User = get_user_model()
    user = (
        User.objects
        .filter(
            email_verification_token=token,
            email_verification_required=True,
        )
        .first()
    )

    if user is None:
        messages.info(
            request,
            "That verification link is no longer active. If you already verified your email, sign in below.",
        )
        return redirect("accounts:login")

    membership = (
        user.studio_memberships
        .select_related("studio")
        .filter(role="administrator", is_active=True)
        .first()
    )

    if verification_is_expired(user):
        intent = None
        if membership is not None:
            intent = StudioSignupIntent.objects.filter(
                studio=membership.studio,
                owner_email=user.email,
            ).first()
        return render(
            request,
            "accounts/registration_verify_expired.html",
            {
                "studio": membership.studio if membership else None,
                "masked_email": _masked_email(user.email),
                "session_id": intent.stripe_checkout_session_id if intent else "",
            },
            status=400,
        )

    user.email_verified_at = timezone.now()
    user.email_verification_required = False
    user.email_verification_token = None
    user.save(
        update_fields=[
            "email_verified_at",
            "email_verification_required",
            "email_verification_token",
        ]
    )

    messages.success(
        request,
        "Email verified. Your Encore workspace is ready — sign in to begin your guided setup.",
    )
    return redirect("accounts:login")

