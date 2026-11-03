from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from registration_portal.models import RegistrationPolicy
from studios.models import Studio, StudioMembership

from .registration_policy_forms import RegistrationPolicyForm


def _admin_workspace(request, studio):
    if request.user.is_superuser:
        return True
    return (
        request.session.get("encore_workspace_role") == "administrator"
        and request.session.get("encore_workspace_studio_slug") == studio.slug
        and request.user.studio_memberships.filter(
            studio=studio,
            role=StudioMembership.Role.ADMINISTRATOR,
            is_active=True,
        ).exists()
    )


def _deny(request, studio):
    return render(
        request,
        "dashboard/access_denied.html",
        {"studio": studio},
        status=403,
    )


@login_required
def registration_policy_list(request, studio_slug):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if not _admin_workspace(request, studio):
        return _deny(request, studio)

    policies = (
        RegistrationPolicy.objects.filter(
            studio=studio,
            is_current=True,
        )
        .prefetch_related("classes")
        .order_by("display_order", "title", "pk")
    )

    return render(
        request,
        "studios/registration_policy_list.html",
        {
            "studio": studio,
            "role": "administrator",
            "settings_section": "registration_policies",
            "policies": policies,
        },
    )


@login_required
@transaction.atomic
def registration_policy_add(request, studio_slug):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if not _admin_workspace(request, studio):
        return _deny(request, studio)

    form = RegistrationPolicyForm(
        request.POST or None,
        studio=studio,
    )
    if request.method == "POST" and form.is_valid():
        policy = form.save(commit=False)
        policy.studio = studio
        policy.created_by = request.user
        policy.version = 1
        policy.is_current = True
        policy.is_required = True
        policy.full_clean(exclude=["classes"])
        policy.save()
        form.save_m2m()
        if policy.scope != RegistrationPolicy.Scope.SPECIFIC_CLASSES:
            policy.classes.clear()

        messages.success(request, f"{policy.title} was created.")
        return redirect(
            "studios:registration_policy_list",
            studio_slug=studio.slug,
        )

    return render(
        request,
        "studios/registration_policy_form.html",
        {
            "studio": studio,
            "role": "administrator",
            "settings_section": "registration_policies",
            "form": form,
            "page_title": "Create Policy or Agreement",
            "page_intro": (
                "Create the exact document families must review during registration, "
                "then choose when it applies."
            ),
            "editing_policy": None,
        },
    )


@login_required
@transaction.atomic
def registration_policy_edit(request, studio_slug, policy_id):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if not _admin_workspace(request, studio):
        return _deny(request, studio)

    policy = get_object_or_404(
        RegistrationPolicy,
        pk=policy_id,
        studio=studio,
        is_current=True,
    )

    initial = {
        "title": policy.title,
        "document_type": policy.document_type,
        "content_html": policy.content_html,
        "acceptance_text": policy.acceptance_text,
        "scope": policy.scope,
        "classes": list(policy.classes.values_list("pk", flat=True)),
        "is_required": policy.is_required,
        "requires_signature": policy.requires_signature,
        "is_active": policy.is_active,
        "effective_date": policy.effective_date,
        "display_order": policy.display_order,
    }
    form = RegistrationPolicyForm(
        request.POST or None,
        studio=studio,
        initial=initial,
    )

    if request.method == "POST" and form.is_valid():
        policy.is_current = False
        policy.save(update_fields=["is_current", "updated_at"])

        new_policy = RegistrationPolicy(
            studio=studio,
            policy_key=policy.policy_key,
            version=policy.version + 1,
            is_current=True,
            title=form.cleaned_data["title"],
            document_type=form.cleaned_data["document_type"],
            content_html=form.cleaned_data["content_html"],
            acceptance_text=form.cleaned_data["acceptance_text"],
            scope=form.cleaned_data["scope"],
            is_required=True,
            requires_signature=form.cleaned_data["requires_signature"],
            is_active=form.cleaned_data["is_active"],
            effective_date=form.cleaned_data["effective_date"],
            display_order=form.cleaned_data.get("display_order") or 0,
            created_by=request.user,
        )
        new_policy.full_clean(exclude=["classes"])
        new_policy.save()
        if new_policy.scope == RegistrationPolicy.Scope.SPECIFIC_CLASSES:
            new_policy.classes.set(form.cleaned_data["classes"])

        messages.success(
            request,
            f"{new_policy.title} was saved as version {new_policy.version}.",
        )
        return redirect(
            "studios:registration_policy_list",
            studio_slug=studio.slug,
        )

    return render(
        request,
        "studios/registration_policy_form.html",
        {
            "studio": studio,
            "role": "administrator",
            "settings_section": "registration_policies",
            "form": form,
            "page_title": f"Edit {policy.title}",
            "page_intro": (
                f"Saving changes creates version {policy.version + 1}; prior acceptance "
                "records keep the exact earlier text."
            ),
            "editing_policy": policy,
        },
    )


@login_required
@transaction.atomic
def registration_policy_toggle(request, studio_slug, policy_id):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if not _admin_workspace(request, studio):
        return _deny(request, studio)

    policy = get_object_or_404(
        RegistrationPolicy,
        pk=policy_id,
        studio=studio,
        is_current=True,
    )
    if request.method == "POST":
        policy.is_active = not policy.is_active
        policy.save(update_fields=["is_active", "updated_at"])
        messages.success(
            request,
            f"{policy.title} is now {'active' if policy.is_active else 'inactive'}.",
        )

    return redirect(
        "studios:registration_policy_list",
        studio_slug=studio.slug,
    )
