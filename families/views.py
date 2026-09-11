from decimal import Decimal
from django.contrib import messages
from urllib.parse import urlencode
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render

from billing.models import FamilyAccount
from students.models import Student
from studios.models import Studio

from .forms import EncoreFamilyForm, GuardianFormSet
from .models import Family, Guardian


def _require_admin(user, studio):
    if user.is_superuser:
        return True

    return user.studio_memberships.filter(
        studio=studio,
        role="administrator",
        is_active=True,
    ).exists()


@login_required
def family_list(request, studio_slug):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if not _require_admin(request.user, studio):
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    requested_view = request.GET.get(
        "view",
        "",
    ).strip()

    if requested_view in {
        "cards",
        "table",
    }:
        view_mode = requested_view
        request.session[
            "encore_family_list_view"
        ] = view_mode
    else:
        view_mode = request.session.get(
            "encore_family_list_view",
            "cards",
        )

        if view_mode not in {
            "cards",
            "table",
        }:
            view_mode = "cards"

    families = (
        Family.objects
        .filter(studio=studio)
        .annotate(
            student_count=Count(
                "students",
                distinct=True,
            ),
            guardian_count=Count(
                "guardians",
                distinct=True,
            ),
        )
        .order_by("family_name", "id")
    )

    search = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()

    if search:
        families = families.filter(
            Q(family_name__icontains=search)
            | Q(guardians__first_name__icontains=search)
            | Q(guardians__last_name__icontains=search)
            | Q(guardians__email__icontains=search)
            | Q(students__first_name__icontains=search)
            | Q(students__last_name__icontains=search)
        ).distinct()

    if status == "active":
        families = families.filter(is_active=True)
    elif status == "inactive":
        families = families.filter(is_active=False)

    family_rows = []

    account_map = {
        account.family_id: account
        for account in (
            FamilyAccount.objects
            .filter(
                studio=studio,
                family__in=families,
            )
            .select_related("family")
        )
    }

    for family in families:
        primary_guardian = (
            Guardian.objects
            .filter(
                family=family,
                is_active=True,
            )
            .order_by("-is_primary", "id")
            .first()
        )

        billing_account = account_map.get(family.id)
        current_balance = (
            billing_account.balance
            if billing_account is not None
            else Decimal("0.00")
        )

        family_rows.append(
            {
                "family": family,
                "primary_guardian": primary_guardian,
                "billing_account": billing_account,
                "current_balance": current_balance,
                "has_balance_due": current_balance > Decimal("0.00"),
            }
        )

    return render(
        request,
        "families/family_list.html",
        {
            "studio": studio,
            "role": "administrator",
            "family_rows": family_rows,
            "filters": {
                "q": search,
                "status": status,
            },
            "view_mode": view_mode,
            "card_view_url": (
                "?"
                + urlencode(
                    {
                        "q": search,
                        "status": status,
                        "view": "cards",
                    }
                )
            ),
            "table_view_url": (
                "?"
                + urlencode(
                    {
                        "q": search,
                        "status": status,
                        "view": "table",
                    }
                )
            ),
        },
    )


@login_required
def family_detail(request, studio_slug, family_id):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if not _require_admin(request.user, studio):
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    family = get_object_or_404(
        Family,
        pk=family_id,
        studio=studio,
    )

    guardians = Guardian.objects.filter(
        family=family,
    ).order_by(
        "-is_primary",
        "last_name",
        "first_name",
    )

    students = Student.objects.filter(
        family=family,
        studio=studio,
    ).order_by(
        "last_name",
        "first_name",
    )

    return render(
        request,
        "families/family_detail.html",
        {
            "studio": studio,
            "role": "administrator",
            "family": family,
            "guardians": guardians,
            "students": students,
        },
    )


@login_required
@transaction.atomic
def family_create(request, studio_slug):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if not _require_admin(request.user, studio):
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    family = Family(studio=studio)

    if request.method == "POST":
        form = EncoreFamilyForm(
            request.POST,
            instance=family,
        )

        formset = GuardianFormSet(
            request.POST,
            instance=family,
        )

        if form.is_valid() and formset.is_valid():
            family = form.save(commit=False)
            family.studio = studio
            family.full_clean()
            family.save()
            form.save_m2m()

            formset.instance = family
            guardians = formset.save(
                commit=False
            )

            for deleted in formset.deleted_objects:
                deleted.delete()

            for guardian in guardians:
                guardian.family = family
                guardian.full_clean()
                guardian.save()

            messages.success(
                request,
                "Family was created.",
            )

            return redirect(
                "families:family_detail",
                studio_slug=studio.slug,
                family_id=family.pk,
            )
    else:
        form = EncoreFamilyForm(
            instance=family,
        )

        formset = GuardianFormSet(
            instance=family,
        )

    return render(
        request,
        "families/family_form.html",
        {
            "studio": studio,
            "role": "administrator",
            "form": form,
            "formset": formset,
            "family": None,
            "page_title": "Add Family",
        },
    )


@login_required
@transaction.atomic
def family_edit(
    request,
    studio_slug,
    family_id,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if not _require_admin(request.user, studio):
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    family = get_object_or_404(
        Family,
        pk=family_id,
        studio=studio,
    )

    if request.method == "POST":
        form = EncoreFamilyForm(
            request.POST,
            instance=family,
        )

        formset = GuardianFormSet(
            request.POST,
            instance=family,
        )

        if form.is_valid() and formset.is_valid():
            family = form.save(commit=False)
            family.full_clean()
            family.save()
            form.save_m2m()

            guardians = formset.save(
                commit=False
            )

            for deleted in formset.deleted_objects:
                deleted.delete()

            for guardian in guardians:
                guardian.family = family
                guardian.full_clean()
                guardian.save()

            messages.success(
                request,
                "Family was updated.",
            )

            return redirect(
                "families:family_detail",
                studio_slug=studio.slug,
                family_id=family.pk,
            )
    else:
        form = EncoreFamilyForm(
            instance=family,
        )

        formset = GuardianFormSet(
            instance=family,
        )

    return render(
        request,
        "families/family_form.html",
        {
            "studio": studio,
            "role": "administrator",
            "form": form,
            "formset": formset,
            "family": family,
            "page_title": "Edit Family",
        },
    )
