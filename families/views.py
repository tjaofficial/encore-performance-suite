from decimal import Decimal
from django.contrib import messages
from django.conf import settings
from django.core.mail import send_mail
from urllib.parse import urlencode
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, OuterRef, Prefetch, Q, Subquery
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from accounts.list_preferences import list_sort_url, paginate_list, resolve_list_sort, resolve_list_view_mode
from billing.models import FamilyAccount
from students.models import Student
from studios.models import Studio

from .forms import (
    EncoreFamilyForm,
    GuardianFormSet,
    ParentFamilyForm,
    ParentGuardianProfileForm,
    ParentGuardianInviteForm,
)
from .models import Family, Guardian
from registration_portal.models import FamilyInvite
from dashboard.parent_portal import parent_portal_context


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

    view_mode = resolve_list_view_mode(
        request,
        studio,
        "families",
        default="table",
    )

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

    primary_guardians = (
        Guardian.objects
        .filter(family=OuterRef("pk"), is_active=True)
        .order_by("-is_primary", "id")
    )
    families = families.annotate(
        primary_guardian_last_name=Subquery(
            primary_guardians.values("last_name")[:1]
        ),
        primary_guardian_first_name=Subquery(
            primary_guardians.values("first_name")[:1]
        ),
        primary_guardian_email=Subquery(
            primary_guardians.values("email")[:1]
        ),
    )
    sort_fields = {
        "family": ("family_name", "id"),
        "guardian": ("primary_guardian_last_name", "primary_guardian_first_name", "family_name"),
        "students": ("student_count", "family_name"),
        "guardians": ("guardian_count", "family_name"),
        "contact": ("primary_guardian_email", "family_name"),
        "balance": ("family_name",),
        "status": ("is_active", "family_name"),
    }
    sort_key, sort_direction = resolve_list_sort(
        request, studio, "families", sort_fields.keys(),
        default_sort="family", default_direction="asc",
    )
    if sort_key == "balance":
        all_families = list(
            families.order_by(
                "family_name",
                "id",
            )
        )
        all_family_ids = [
            family.pk
            for family in all_families
        ]

        balance_accounts = (
            FamilyAccount.objects
            .filter(
                studio=studio,
                family_id__in=all_family_ids,
            )
            .prefetch_related(
                "charges__payment_allocations",
                "charges__credit_allocations",
                "credits__allocations",
            )
        )

        balance_map = {}

        for account in balance_accounts:
            open_balance = Decimal("0.00")

            for charge in account.charges.all():
                if charge.status not in {
                    "open",
                    "partially_paid",
                }:
                    continue

                paid_amount = sum(
                    (
                        allocation.amount
                        for allocation
                        in charge.payment_allocations.all()
                    ),
                    Decimal("0.00"),
                )
                credit_amount = sum(
                    (
                        allocation.amount
                        for allocation
                        in charge.credit_allocations.all()
                    ),
                    Decimal("0.00"),
                )
                remaining = (
                    charge.amount
                    - paid_amount
                    - credit_amount
                )
                open_balance += max(
                    remaining,
                    Decimal("0.00"),
                )

            unapplied_credit = Decimal("0.00")

            for credit in account.credits.all():
                if credit.is_void:
                    continue

                allocated_amount = sum(
                    (
                        allocation.amount
                        for allocation
                        in credit.allocations.all()
                    ),
                    Decimal("0.00"),
                )
                unapplied_credit += max(
                    credit.amount
                    - allocated_amount,
                    Decimal("0.00"),
                )

            balance_map[
                account.family_id
            ] = (
                open_balance
                - unapplied_credit
            )

        all_families.sort(
            key=lambda family: (
                balance_map.get(
                    family.pk,
                    Decimal("0.00"),
                ),
                family.family_name.lower(),
                family.pk,
            ),
            reverse=(
                sort_direction == "desc"
            ),
        )
        families = all_families
    else:
        order_fields = list(
            sort_fields[sort_key]
        )
        if sort_direction == "desc":
            order_fields = [
                f"-{field}"
                for field in order_fields
            ]
        families = families.order_by(
            *order_fields
        )
    sort_columns = {
        key: {
            "url": list_sort_url(request, key, sort_key, sort_direction),
            "active": sort_key == key,
            "direction": sort_direction if sort_key == key else "",
        }
        for key in sort_fields
    }

    page_obj, pagination_context = paginate_list(
        request,
        studio,
        "families",
        families,
        default_page_size=50,
    )

    page_family_ids = [
        family.pk
        for family in page_obj.object_list
    ]

    page_families = (
        Family.objects
        .filter(
            studio=studio,
            pk__in=page_family_ids,
        )
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
        .prefetch_related(
            Prefetch(
                "guardians",
                queryset=(
                    Guardian.objects
                    .filter(is_active=True)
                    .order_by(
                        "-is_primary",
                        "id",
                    )
                ),
                to_attr="active_guardians_for_list",
            )
        )
    )

    family_by_id = {
        family.pk: family
        for family in page_families
    }

    account_map = {
        account.family_id: account
        for account in (
            FamilyAccount.objects
            .filter(
                studio=studio,
                family_id__in=page_family_ids,
            )
            .select_related("family")
        )
    }

    family_rows = []

    for family_id in page_family_ids:
        family = family_by_id.get(family_id)
        if family is None:
            continue

        primary_guardian = (
            family.active_guardians_for_list[0]
            if family.active_guardians_for_list
            else None
        )

        billing_account = account_map.get(
            family.id
        )
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
                "has_balance_due": (
                    current_balance
                    > Decimal("0.00")
                ),
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
            "sort_columns": sort_columns,
            "sort_key": sort_key,
            "sort_direction": sort_direction,
            "card_view_url": (
                "?"
                + urlencode(
                    {
                        "q": search,
                        "status": status,
                        "view": "cards",
                        "page_size": pagination_context[
                            "page_size"
                        ],
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
                        "page_size": pagination_context[
                            "page_size"
                        ],
                    }
                )
            ),
            **pagination_context,
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



def _parent_guardian(request, studio):
    return (
        Guardian.objects
        .filter(
            family__studio=studio,
            user=request.user,
            is_active=True,
        )
        .select_related("family")
        .order_by("-is_primary", "pk")
        .first()
    )


def _primary_parent_guardian(request, studio):
    guardian = _parent_guardian(request, studio)

    if guardian is None or not guardian.is_primary:
        return None

    return guardian


@login_required
def parent_family_detail(request, studio_slug):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    guardian = _parent_guardian(request, studio)

    if guardian is None:
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    family = guardian.family
    guardians = (
        family.guardians
        .filter(is_active=True)
        .select_related("user")
        .order_by("-is_primary", "last_name", "first_name")
    )

    context = {
        "studio": studio,
        "role": "family",
        "guardians": guardians,
        "can_manage_family": guardian.is_primary,
    }
    context.update(
        parent_portal_context(
            request,
            studio,
            section="family",
        )
    )

    return render(
        request,
        "families/parent_family_detail.html",
        context,
    )


@login_required
def parent_family_edit(request, studio_slug):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    guardian = _primary_parent_guardian(
        request,
        studio,
    )

    if guardian is None:
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    family = guardian.family
    form = ParentFamilyForm(
        request.POST or None,
        instance=family,
    )

    if request.method == "POST" and form.is_valid():
        family = form.save()

        if guardian.is_primary:
            family.primary_contact_first_name = (
                guardian.first_name
            )
            family.primary_contact_last_name = (
                guardian.last_name
            )
            family.save(
                update_fields=[
                    "primary_contact_first_name",
                    "primary_contact_last_name",
                    "updated_at",
                ]
            )

        messages.success(
            request,
            "Family information updated.",
        )

        return redirect(
            "families:parent_family_detail",
            studio_slug=studio.slug,
        )

    context = {
        "studio": studio,
        "role": "family",
        "form": form,
    }
    context.update(
        parent_portal_context(
            request,
            studio,
            section="family",
        )
    )

    return render(
        request,
        "families/parent_family_form.html",
        context,
    )


@login_required
def parent_guardian_add(request, studio_slug):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    current_guardian = _primary_parent_guardian(
        request,
        studio,
    )

    if current_guardian is None:
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    family = current_guardian.family
    guardian = Guardian(
        family=family,
        is_primary=False,
        is_active=True,
    )

    form = ParentGuardianProfileForm(
        request.POST or None,
        instance=guardian,
    )

    if request.method == "POST" and form.is_valid():
        new_guardian = form.save(commit=False)
        new_guardian.family = family
        new_guardian.is_primary = False
        new_guardian.is_active = True
        new_guardian.user = None
        new_guardian.full_clean()
        new_guardian.save()

        messages.success(
            request,
            (
                f"{new_guardian.first_name} "
                f"{new_guardian.last_name} was added "
                "to the family without a separate login."
            ),
        )

        return redirect(
            "families:parent_family_detail",
            studio_slug=studio.slug,
        )

    context = {
        "studio": studio,
        "role": "family",
        "form": form,
    }
    context.update(
        parent_portal_context(
            request,
            studio,
            section="family",
        )
    )

    return render(
        request,
        "families/parent_guardian_form.html",
        context,
    )


@login_required
def parent_guardian_invite(request, studio_slug):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    current_guardian = _primary_parent_guardian(
        request,
        studio,
    )

    if current_guardian is None:
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    family = current_guardian.family
    form = ParentGuardianInviteForm(
        request.POST or None,
    )

    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"].strip().lower()

        linked_guardian = (
            Guardian.objects
            .filter(
                family=family,
                email__iexact=email,
                is_active=True,
            )
            .select_related("user")
            .first()
        )

        if linked_guardian is not None and linked_guardian.user_id:
            form.add_error(
                "email",
                "This guardian already has an Encore login for this family.",
            )
        elif FamilyInvite.objects.filter(
            studio=studio,
            family=family,
            email__iexact=email,
            accepted_at__isnull=True,
            expires_at__gt=timezone.now(),
        ).exists():
            form.add_error(
                "email",
                "An active invitation has already been sent to this email.",
            )
        else:
            if linked_guardian is None:
                linked_guardian = Guardian.objects.create(
                    family=family,
                    first_name=form.cleaned_data["first_name"],
                    last_name=form.cleaned_data["last_name"],
                    relationship=form.cleaned_data["relationship"],
                    email=email,
                    phone=form.cleaned_data["phone"],
                    is_primary=False,
                    is_authorized_for_pickup=form.cleaned_data[
                        "is_authorized_for_pickup"
                    ],
                    is_financially_responsible=form.cleaned_data[
                        "is_financially_responsible"
                    ],
                    is_active=True,
                )
            else:
                linked_guardian.first_name = form.cleaned_data["first_name"]
                linked_guardian.last_name = form.cleaned_data["last_name"]
                linked_guardian.relationship = form.cleaned_data["relationship"]
                linked_guardian.phone = form.cleaned_data["phone"]
                linked_guardian.is_authorized_for_pickup = form.cleaned_data[
                    "is_authorized_for_pickup"
                ]
                linked_guardian.is_financially_responsible = form.cleaned_data[
                    "is_financially_responsible"
                ]
                linked_guardian.save()

            invite = FamilyInvite.objects.create(
                studio=studio,
                email=email,
                guardian_first_name=linked_guardian.first_name,
                guardian_last_name=linked_guardian.last_name,
                family=family,
                created_by=request.user,
            )

            invite_path = reverse(
                "registration_portal:accept_invite",
                kwargs={"token": invite.token},
            )
            invite_url = (
                f"{getattr(settings, 'ENCORE_BASE_URL', '').rstrip('/')}"
                f"{invite_path}"
            )

            from communications.studio_email import send_studio_email
            from django.utils.html import escape
            invite_body = (
                f"{current_guardian.first_name} {current_guardian.last_name} invited you "
                f"to join their family account for {studio.name}.\n\n"
                f"Create your Encore login here:\n{invite_url}\n\n"
                f"This link expires on {invite.expires_at:%B %d, %Y}."
            )
            send_studio_email(
                studio=studio, to=[invite.email],
                subject=f"You're invited to {studio.name} on Encore",
                html_body=f'<div style="white-space:pre-line">{escape(invite_body)}</div>',
                text_body=invite_body, sensitive=True,
                tags={'message_type': 'family_invitation'},
            )

            messages.success(
                request,
                f"Invitation sent to {invite.email}.",
            )

            return redirect(
                "families:parent_family_detail",
                studio_slug=studio.slug,
            )

    context = {
        "studio": studio,
        "role": "family",
        "form": form,
    }
    context.update(
        parent_portal_context(
            request,
            studio,
            section="family",
        )
    )

    return render(
        request,
        "families/parent_guardian_invite.html",
        context,
    )
