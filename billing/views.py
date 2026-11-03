from datetime import datetime, time, timedelta
from decimal import Decimal
import logging

from urllib.parse import urlencode
import stripe
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.core.exceptions import ValidationError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from studios.models import Studio
from families.models import Guardian
from dashboard.parent_portal import parent_portal_context

from .forms import (
    CancelSubscriptionForm,
    ChargeForm,
    CreditForm,
    DrawingBoardChangeForm,
    PaymentForm,
    SubscriptionPlanChangeForm,
    TuitionPlanForm,
    StudioTuitionSettingsForm,
    BaseTuitionRateTierFormSet,
    AdministratorRefundForm,
)
from .models import (
    Charge,
    FamilyAccount,
    PaymentRefund,
    StudioSignupIntent,
    StudioSubscription,
    SubscriptionNotice,
    TuitionPlan,
    StudioTuitionSettings,
)
from .subscription_services import (
    apply_renewal_state,
    cancel_subscription_at_period_end,
    configure_stripe,
    create_subscription_notice,
    evaluate_student_band_change,
    price_catalog_rows,
    request_drawing_board_change,
    request_plan_change,
    resume_subscription,
    send_subscription_email,
    stripe_metadata,
    stripe_value,
    subscription_price,
)

from .services import (
    allocate_credit_to_oldest_open_charges,
    allocate_payment_to_oldest_open_charges,
    generate_due_recurring_charges,
)

from .connect_services import (
    create_account_link,
    subscription_for_connected_account,
    sync_connected_account,
)
from .stripe_environment import stripe_mode, connected_account_for_subscription, verify_connected_account
from .autopay_services import current_profile, create_setup_intent, activate_from_setup, disable_autopay, collect_activation_balance_once

from .parent_payment_services import (
    FAMILY_BALANCE_PAYMENT_KIND,
    create_family_balance_payment_intent,
    finalize_family_balance_payment,
)


def _require_admin(user, studio):
    if user.is_superuser:
        return True

    return user.studio_memberships.filter(
        studio=studio,
        role="administrator",
        is_active=True,
    ).exists()


def _account_for_studio(studio, account_id):
    return get_object_or_404(
        FamilyAccount.objects.select_related(
            "family",
            "studio",
        ),
        pk=account_id,
        studio=studio,
    )


@login_required
def account_detail(request, studio_slug, account_id):
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

    account = _account_for_studio(studio, account_id)

    charges = (
        account.charges
        .select_related(
            "student",
            "class_instance",
            "enrollment",
        )
        .order_by("-created_at")
    )

    payments = account.payments.all().order_by("-paid_at")
    refunds = PaymentRefund.objects.filter(payment__account=account).select_related("charge", "payment", "requested_by")

    credits = (
        account.credits
        .select_related("student")
        .order_by("-created_at")
    )

    recurring_schedules = (
        account.recurring_schedules
        .select_related(
            "enrollment",
            "student",
            "class_instance",
            "season",
            "tuition_plan",
        )
        .order_by(
            "-is_active",
            "next_charge_date",
        )
    )

    ledger_rows = []

    for charge in charges:
        ledger_rows.append(
            {
                "date": charge.created_at,
                "kind": "Charge",
                "description": charge.description,
                "amount": charge.amount,
                "direction": "debit",
                "status": charge.get_status_display(),
            }
        )

    for payment in payments:
        ledger_rows.append(
            {
                "date": payment.paid_at,
                "kind": "Payment",
                "description": payment.get_method_display(),
                "amount": payment.amount,
                "direction": "credit",
                "status": payment.get_status_display(),
            }
        )

    for credit in credits:
        ledger_rows.append(
            {
                "date": credit.created_at,
                "kind": "Credit",
                "description": credit.description,
                "amount": credit.amount,
                "direction": "credit",
                "status": "Void" if credit.is_void else "Active",
            }
        )

    ledger_rows.sort(
        key=lambda row: row["date"],
        reverse=True,
    )

    return render(
        request,
        "billing/account_detail.html",
        {
            "studio": studio,
            "role": "administrator",
            "account": account,
            "charges": charges,
            "payments": payments,
            "refunds": refunds,
            "credits": credits,
            "recurring_schedules": recurring_schedules,
            "ledger_rows": ledger_rows,
        },
    )



@login_required
def issue_refund(request, studio_slug, account_id):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if not _require_admin(request.user, studio):
        return render(request, "dashboard/access_denied.html", {"studio": studio}, status=403)
    account = _account_for_studio(studio, account_id)
    form = AdministratorRefundForm(request.POST or None, account=account)
    if request.method == "POST" and form.is_valid() and request.POST.get("confirm_refund") == "yes":
        allocation = form.cleaned_data["allocation"]
        from .refund_services import request_refund
        try:
            refund = request_refund(account=account, payment=allocation.payment, charge=allocation.charge,
                amount=form.cleaned_data["amount"], reason=form.cleaned_data["reason"],
                notes=form.cleaned_data["notes"], admin=request.user)
        except (ValidationError, ValueError) as exc:
            form.add_error(None, "; ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc))
        else:
            messages.success(request, f"Stripe refund #{refund.pk} recorded as {refund.get_status_display()}. Check status before promising a refund to the family.")
            return redirect("billing:account_detail", studio_slug=studio.slug, account_id=account.pk)
    return render(request, "billing/issue_refund.html", {
        "studio": studio, "role": "administrator", "account": account, "form": form,
    })

@login_required
def add_charge(request, studio_slug, account_id):
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

    account = _account_for_studio(studio, account_id)

    form = ChargeForm(
        request.POST or None,
        account=account,
    )

    if request.method == "POST" and form.is_valid():
        charge = form.save(commit=False)
        charge.account = account
        charge.full_clean()
        charge.save()

        messages.success(request, "Charge added.")

        return redirect(
            "billing:account_detail",
            studio_slug=studio.slug,
            account_id=account.pk,
        )

    return render(
        request,
        "billing/simple_form.html",
        {
            "studio": studio,
            "role": "administrator",
            "account": account,
            "form": form,
            "page_title": "Add Charge",
            "submit_label": "Add Charge",
        },
    )


@login_required
def record_payment(request, studio_slug, account_id):
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

    account = _account_for_studio(studio, account_id)

    form = PaymentForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        payment = form.save(commit=False)
        payment.account = account
        payment.full_clean()
        payment.save()

        if (
            form.cleaned_data.get("auto_allocate")
            and payment.status == payment.Status.SUCCEEDED
        ):
            allocate_payment_to_oldest_open_charges(payment)

        messages.success(request, "Payment recorded.")

        return redirect(
            "billing:account_detail",
            studio_slug=studio.slug,
            account_id=account.pk,
        )

    return render(
        request,
        "billing/simple_form.html",
        {
            "studio": studio,
            "role": "administrator",
            "account": account,
            "form": form,
            "page_title": "Record Payment",
            "submit_label": "Record Payment",
        },
    )


@login_required
def add_credit(request, studio_slug, account_id):
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

    account = _account_for_studio(studio, account_id)

    form = CreditForm(
        request.POST or None,
        account=account,
    )

    if request.method == "POST" and form.is_valid():
        credit = form.save(commit=False)
        credit.account = account
        credit.full_clean()
        credit.save()

        if form.cleaned_data.get("auto_allocate"):
            allocate_credit_to_oldest_open_charges(credit)

        messages.success(request, "Credit added.")

        return redirect(
            "billing:account_detail",
            studio_slug=studio.slug,
            account_id=account.pk,
        )

    return render(
        request,
        "billing/simple_form.html",
        {
            "studio": studio,
            "role": "administrator",
            "account": account,
            "form": form,
            "page_title": "Add Credit",
            "submit_label": "Add Credit",
        },
    )


@login_required
def tuition_plan_list(request, studio_slug):
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

    tuition_settings, _ = StudioTuitionSettings.objects.get_or_create(studio=studio)

    if request.method == "POST" and "save_tuition_settings" in request.POST:
        tuition_settings_form = StudioTuitionSettingsForm(
            request.POST, instance=tuition_settings, studio=studio
        )
        tier_formset = BaseTuitionRateTierFormSet(
            request.POST, instance=tuition_settings, prefix="tiers"
        )
        forms_valid = tuition_settings_form.is_valid() and tier_formset.is_valid()
        if forms_valid:
            candidate = tuition_settings_form.save(commit=False)
            if (
                candidate.pricing_mode == StudioTuitionSettings.PricingMode.STUDIO_WIDE
                and candidate.studio_wide_method
                == StudioTuitionSettings.StudioWideMethod.TIERED_HOURLY
            ):
                active_tiers = [
                    form
                    for form in tier_formset.forms
                    if form.cleaned_data
                    and not form.cleaned_data.get("DELETE")
                    and form.cleaned_data.get("hour_number") is not None
                    and form.cleaned_data.get("hourly_rate") is not None
                ]
                if not active_tiers:
                    tuition_settings_form.add_error(
                        None,
                        "Add at least one hourly rate tier for tiered studio-wide tuition.",
                    )
                    forms_valid = False
        if forms_valid:
            tuition_settings = tuition_settings_form.save()
            tier_formset.instance = tuition_settings
            tier_formset.save()
            messages.success(request, "Tuition settings updated.")
            return redirect("billing:tuition_plan_list", studio_slug=studio.slug)
    else:
        tuition_settings_form = StudioTuitionSettingsForm(
            instance=tuition_settings, studio=studio
        )
        tier_formset = BaseTuitionRateTierFormSet(
            instance=tuition_settings, prefix="tiers"
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
            "encore_billing_policy_list_view"
        ] = view_mode
    else:
        view_mode = request.session.get(
            "encore_billing_policy_list_view",
            "cards",
        )

        if view_mode not in {
            "cards",
            "table",
        }:
            view_mode = "cards"

    plans = (
        TuitionPlan.objects
        .filter(studio=studio)
        .annotate(
            schedule_count=Count(
                "recurring_schedules",
            ),
            class_count=Count(
                "classes",
                distinct=True,
            ),
        )
        .order_by("name")
    )

    return render(
        request,
        "billing/tuition_plan_list.html",
        {
            "studio": studio,
            "role": "administrator",
            "plans": plans,
            "tuition_settings": tuition_settings,
            "tuition_settings_form": tuition_settings_form,
            "tier_formset": tier_formset,
            "view_mode": view_mode,
            "card_view_url": (
                "?"
                + urlencode(
                    {
                        "view": "cards",
                    }
                )
            ),
            "settings_section": "billing_policies",
            "table_view_url": (
                "?"
                + urlencode(
                    {
                        "view": "table",
                    }
                )
            ),
        },
    )


@login_required
def tuition_plan_create(request, studio_slug):
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

    plan = TuitionPlan(studio=studio)

    form = TuitionPlanForm(
        request.POST or None,
        instance=plan,
    )

    if request.method == "POST" and form.is_valid():
        plan = form.save(commit=False)
        plan.studio = studio
        plan.full_clean()
        plan.save()

        messages.success(
            request,
            "Tuition billing policy created.",
        )

        return redirect(
            "billing:tuition_plan_list",
            studio_slug=studio.slug,
        )

    return render(
        request,
        "billing/tuition_plan_form.html",
        {
            "studio": studio,
            "role": "administrator",
            "form": form,
            "plan": None,
            "page_title": "Add Tuition Billing Policy",
            "settings_section": "billing_policies",
        },
    )


@login_required
def tuition_plan_edit(
    request,
    studio_slug,
    plan_id,
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

    plan = get_object_or_404(
        TuitionPlan,
        pk=plan_id,
        studio=studio,
    )

    form = TuitionPlanForm(
        request.POST or None,
        instance=plan,
    )

    if request.method == "POST" and form.is_valid():
        plan = form.save(commit=False)
        plan.full_clean()
        plan.save()

        messages.success(
            request,
            "Tuition billing policy updated.",
        )

        return redirect(
            "billing:tuition_plan_list",
            studio_slug=studio.slug,
        )

    return render(
        request,
        "billing/tuition_plan_form.html",
        {
            "studio": studio,
            "role": "administrator",
            "form": form,
            "plan": plan,
            "page_title": "Edit Tuition Billing Policy",
            "settings_section": "billing_policies",
        },
    )


@login_required
def run_recurring_billing(request, studio_slug):
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

    if request.method != "POST":
        return redirect(
            "billing:tuition_plan_list",
            studio_slug=studio.slug,
        )

    result = generate_due_recurring_charges(
        studio=studio,
        as_of_date=timezone.localdate(),
    )

    messages.success(
        request,
        (
            f"Recurring billing complete: "
            f"{result['created']} charge(s) created, "
            f"{result['skipped']} duplicate(s) skipped."
        ),
    )

    return redirect(
        "billing:tuition_plan_list",
        studio_slug=studio.slug,
    )


@login_required
def studio_subscription(request, studio_slug):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if not _require_admin(
        request.user,
        studio,
    ):
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    subscription = get_object_or_404(
        StudioSubscription,
        studio=studio,
    )

    # Read Stripe Accounts v2 capabilities rather than legacy v1 booleans.
    from .stripe_activation import account_readiness
    try:
        connect_status = account_readiness(subscription)
    except (ValueError, stripe.error.StripeError, AttributeError) as exc:
        logging.getLogger(__name__).warning('Unable to load Connect readiness for studio %s: %s', studio.pk, exc)
        connect_status = {"ready": False, "account_setup": False,
                          "charges_enabled": False, "payouts_enabled": False,
                          "message": "Stripe status could not be verified. Open Payment Activation to retry.",
                          "mode": stripe_mode(), "requirements": []}

    evaluate_student_band_change(
        subscription
    )

    subscription.refresh_from_db()

    student_count = studio.students.count()

    notices = list(
        studio.subscription_notices
        .filter(
            is_read=False,
        )
        .order_by(
            "-created_at",
        )
    )

    current_software_price = subscription_price(
        subscription.plan_tier,
        subscription.student_band,
        drawing_board=False,
    )

    current_drawing_board_price = (
        Decimal("39.00")
        if subscription.drawing_board_enabled
        else Decimal("0.00")
    )

    pending_plan_tier = (
        subscription.pending_plan_tier
        or subscription.plan_tier
    )

    pending_student_band = (
        subscription.pending_student_band
        or subscription.student_band
    )

    if (
        subscription.pending_drawing_board_enabled
        is None
    ):
        pending_drawing_board_enabled = (
            subscription.drawing_board_enabled
        )
    else:
        pending_drawing_board_enabled = (
            subscription.pending_drawing_board_enabled
        )

    next_software_price = subscription_price(
        pending_plan_tier,
        pending_student_band,
        drawing_board=False,
    )

    next_drawing_board_price = (
        Decimal("39.00")
        if pending_drawing_board_enabled
        else Decimal("0.00")
    )

    next_monthly_total = subscription_price(
        pending_plan_tier,
        pending_student_band,
        drawing_board=(
            pending_drawing_board_enabled
        ),
    )

    has_pending_change = bool(
        subscription.pending_plan_tier
        or subscription.pending_student_band
        or (
            subscription.pending_drawing_board_enabled
            is not None
        )
    )

    pending_band_label = ""

    if subscription.pending_student_band:
        pending_band_label = next(
            (
                row["label"]
                for row in price_catalog_rows()
                if row["key"]
                == subscription.pending_student_band
            ),
            subscription.pending_student_band,
        )

    current_band_label = next(
        (
            row["label"]
            for row in price_catalog_rows()
            if row["key"]
            == subscription.student_band
        ),
        subscription.student_band,
    )

    normalized_notices = []

    for notice in notices:
        notice_message = notice.message

        if (
            notice.notice_type
            == SubscriptionNotice.NoticeType.PRICE_CHANGE
            and subscription.pending_student_band
            and next_monthly_total is not None
        ):
            notice_message = (
                f"Encore now counts {student_count} student records. "
                f"At your next billing cycle, your student band will "
                f"change from {current_band_label} to {pending_band_label}. "
                f"Your current monthly total is "
                f"${subscription.current_monthly_price:.2f}. "
                f"Your next monthly total will be "
                f"${next_monthly_total:.2f}."
            )

            if pending_drawing_board_enabled:
                notice_message += (
                    " This total includes Drawing Board."
                )

        normalized_notices.append(
            {
                "id": notice.id,
                "title": (
                    "Student pricing change scheduled"
                    if (
                        notice.notice_type
                        == SubscriptionNotice.NoticeType.PRICE_CHANGE
                        and subscription.pending_student_band
                    )
                    else notice.title
                ),
                "message": notice_message,
            }
        )

    plan_form = SubscriptionPlanChangeForm(
        current_plan=subscription.plan_tier,
        initial={
            "plan_tier": pending_plan_tier,
        },
    )

    drawing_form = DrawingBoardChangeForm(
        initial={
            "enabled": (
                pending_drawing_board_enabled
            )
        }
    )

    cancel_form = CancelSubscriptionForm()

    return render(
        request,
        "billing/studio_subscription.html",
        {
            "studio": studio,
            "role": "administrator",
            "subscription": subscription,
            "student_count": student_count,
            "pricing_rows": price_catalog_rows(),
            "current_software_price": current_software_price,
            "current_drawing_board_price": current_drawing_board_price,
            "next_software_price": next_software_price,
            "next_drawing_board_price": next_drawing_board_price,
            "next_monthly_total": next_monthly_total,
            "has_pending_change": has_pending_change,
            "pending_plan_tier": pending_plan_tier,
            "pending_student_band": pending_student_band,
            "pending_drawing_board_enabled": pending_drawing_board_enabled,
            "current_band_label": current_band_label,
            "pending_band_label": pending_band_label,
            "plan_form": plan_form,
            "drawing_form": drawing_form,
            "cancel_form": cancel_form,
            "notices": normalized_notices,
            "drawing_board_price": 39,
            "settings_section": "subscription",
            "connect_status": connect_status,
        },
    )


def _stripe_invoice_datetime(timestamp):
    if not timestamp:
        return None

    return datetime.fromtimestamp(
        timestamp,
        tz=timezone.get_current_timezone(),
    )


def _stripe_invoice_amount(value):
    return (
        Decimal(str(value or 0))
        / Decimal("100")
    )


def _invoice_line_summary(invoice):
    lines = stripe_value(invoice, "lines")
    data = stripe_value(lines, "data", []) if lines else []

    descriptions = []

    for line in data or []:
        description = stripe_value(
            line,
            "description",
            "",
        )

        if (
            description
            and description not in descriptions
        ):
            descriptions.append(description)

        if len(descriptions) == 2:
            break

    if descriptions:
        return " · ".join(descriptions)

    billing_reason = stripe_value(
        invoice,
        "billing_reason",
        "",
    )

    labels = {
        "subscription_create": "Subscription started",
        "subscription_cycle": "Monthly subscription",
        "subscription_update": "Subscription change / proration",
        "manual": "Manual invoice",
    }

    return labels.get(
        billing_reason,
        "Encore subscription",
    )


def _stripe_invoice_row(invoice):
    created = _stripe_invoice_datetime(
        stripe_value(invoice, "created")
    )

    period_start = _stripe_invoice_datetime(
        stripe_value(invoice, "period_start")
    )

    period_end = _stripe_invoice_datetime(
        stripe_value(invoice, "period_end")
    )

    status = stripe_value(
        invoice,
        "status",
        "draft",
    )

    collection_method = stripe_value(
        invoice,
        "collection_method",
        "",
    )

    return {
        "id": stripe_value(invoice, "id", ""),
        "number": stripe_value(invoice, "number", "") or "Draft",
        "created": created,
        "period_start": period_start,
        "period_end": period_end,
        "description": _invoice_line_summary(invoice),
        "status": status,
        "status_label": str(status).replace("_", " ").title(),
        "total": _stripe_invoice_amount(
            stripe_value(invoice, "total", 0)
        ),
        "amount_paid": _stripe_invoice_amount(
            stripe_value(invoice, "amount_paid", 0)
        ),
        "amount_remaining": _stripe_invoice_amount(
            stripe_value(invoice, "amount_remaining", 0)
        ),
        "currency": str(
            stripe_value(invoice, "currency", "usd")
        ).upper(),
        "collection_method": collection_method,
        "collection_label": (
            "Automatic payment"
            if collection_method == "charge_automatically"
            else "Invoice"
        ),
        "billing_reason": str(
            stripe_value(invoice, "billing_reason", "")
        ).replace("_", " ").title(),
        "hosted_invoice_url": stripe_value(
            invoice,
            "hosted_invoice_url",
            "",
        ),
        "invoice_pdf": stripe_value(
            invoice,
            "invoice_pdf",
            "",
        ),
    }


@login_required
def billing_history(request, studio_slug):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if not _require_admin(
        request.user,
        studio,
    ):
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    subscription = get_object_or_404(
        StudioSubscription,
        studio=studio,
    )

    date_from_raw = request.GET.get(
        "date_from",
        "",
    ).strip()

    date_to_raw = request.GET.get(
        "date_to",
        "",
    ).strip()

    invoice_query = request.GET.get(
        "invoice",
        "",
    ).strip()

    status_filter = request.GET.get(
        "status",
        "",
    ).strip().lower()

    valid_statuses = {
        "",
        "draft",
        "open",
        "paid",
        "uncollectible",
        "void",
    }

    if status_filter not in valid_statuses:
        status_filter = ""

    date_from = None
    date_to = None

    try:
        if date_from_raw:
            date_from = datetime.strptime(
                date_from_raw,
                "%Y-%m-%d",
            ).date()

        if date_to_raw:
            date_to = datetime.strptime(
                date_to_raw,
                "%Y-%m-%d",
            ).date()
    except ValueError:
        messages.error(
            request,
            "Use valid dates in the billing history filters.",
        )
        date_from = None
        date_to = None

    if (
        date_from
        and date_to
        and date_from > date_to
    ):
        messages.error(
            request,
            "The From date cannot be after the To date.",
        )
        date_from = None
        date_to = None

    invoice_rows = []
    stripe_error = ""
    truncated = False

    if not subscription.stripe_customer_id:
        stripe_error = (
            "This studio does not have a Stripe customer ID yet, "
            "so there is no Stripe billing history to display."
        )
    else:
        try:
            configure_stripe()

            params = {
                "customer": subscription.stripe_customer_id,
                "limit": 100,
            }

            created_filter = {}

            if date_from:
                start_dt = timezone.make_aware(
                    datetime.combine(
                        date_from,
                        time.min,
                    ),
                    timezone.get_current_timezone(),
                )
                created_filter["gte"] = int(
                    start_dt.timestamp()
                )

            if date_to:
                end_dt = timezone.make_aware(
                    datetime.combine(
                        date_to + timedelta(days=1),
                        time.min,
                    ),
                    timezone.get_current_timezone(),
                )
                created_filter["lt"] = int(
                    end_dt.timestamp()
                )

            if created_filter:
                params["created"] = created_filter

            invoices = stripe.Invoice.list(
                **params
            )

            query_lower = invoice_query.lower()

            for index, invoice in enumerate(
                invoices.auto_paging_iter()
            ):
                if index >= 500:
                    truncated = True
                    break

                row = _stripe_invoice_row(
                    invoice
                )

                if (
                    query_lower
                    and query_lower
                    not in row["number"].lower()
                    and query_lower
                    not in row["id"].lower()
                ):
                    continue

                if (
                    status_filter
                    and row["status"] != status_filter
                ):
                    continue

                invoice_rows.append(row)

        except Exception:
            logging.getLogger(__name__).exception(
                "Unable to load Stripe billing history for studio %s",
                studio.pk,
            )
            stripe_error = (
                "Encore could not load billing history from Stripe "
                "right now. Please try again in a moment."
            )

    return render(
        request,
        "billing/billing_history.html",
        {
            "studio": studio,
            "role": "administrator",
            "subscription": subscription,
            "invoices": invoice_rows,
            "stripe_error": stripe_error,
            "truncated": truncated,
            "date_from": date_from_raw,
            "date_to": date_to_raw,
            "invoice_query": invoice_query,
            "status_filter": status_filter,
            "settings_section": "billing_history",
        },
    )


@login_required
def change_subscription_plan(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if not _require_admin(
        request.user,
        studio,
    ):
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    if request.method != "POST":
        return redirect(
            "billing:studio_subscription",
            studio_slug=studio.slug,
        )

    subscription = get_object_or_404(
        StudioSubscription,
        studio=studio,
    )

    form = SubscriptionPlanChangeForm(
        request.POST,
        current_plan=subscription.plan_tier,
    )

    if form.is_valid():
        result = request_plan_change(
            subscription,
            form.cleaned_data[
                "plan_tier"
            ],
        )

        if result == "upgraded":
            messages.success(
                request,
                (
                    "Your Encore plan was upgraded immediately. "
                    "Stripe charged the prorated difference for the "
                    "remainder of the current billing period."
                ),
            )

        elif result == "downgrade_scheduled":
            messages.success(
                request,
                (
                    "Your downgrade is scheduled for the next "
                    "billing cycle. You keep your current Pro "
                    "features until then."
                ),
            )

        elif result == "downgrade_cancelled":
            messages.success(
                request,
                (
                    "Your scheduled downgrade was cancelled. "
                    "Your current plan will continue."
                ),
            )

        else:
            messages.info(
                request,
                "Your plan did not change.",
            )

    return redirect(
        "billing:studio_subscription",
        studio_slug=studio.slug,
    )


@login_required
def change_drawing_board(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if not _require_admin(
        request.user,
        studio,
    ):
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    if request.method != "POST":
        return redirect(
            "billing:studio_subscription",
            studio_slug=studio.slug,
        )

    subscription = get_object_or_404(
        StudioSubscription,
        studio=studio,
    )

    form = DrawingBoardChangeForm(
        request.POST,
    )

    if form.is_valid():
        enabled = form.cleaned_data[
            "enabled"
        ]

        result = request_drawing_board_change(
            subscription,
            enabled,
        )

        if result == "added":
            messages.success(
                request,
                (
                    "Drawing Board is now active. "
                    "Stripe charged the prorated amount for the "
                    "remainder of the current billing period."
                ),
            )

        elif result == "removal_scheduled":
            messages.success(
                request,
                (
                    "Drawing Board will be removed at the end "
                    "of the current billing period. "
                    "You keep access until then."
                ),
            )

        elif result == "removal_cancelled":
            messages.success(
                request,
                (
                    "The scheduled Drawing Board removal was "
                    "cancelled. Your add-on will continue."
                ),
            )

        else:
            messages.info(
                request,
                "Drawing Board did not change.",
            )

    return redirect(
        "billing:studio_subscription",
        studio_slug=studio.slug,
    )


@login_required
def cancel_studio_subscription(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if not _require_admin(
        request.user,
        studio,
    ):
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    if request.method != "POST":
        return redirect(
            "billing:studio_subscription",
            studio_slug=studio.slug,
        )

    subscription = get_object_or_404(
        StudioSubscription,
        studio=studio,
    )

    form = CancelSubscriptionForm(
        request.POST,
    )

    if form.is_valid():
        cancel_subscription_at_period_end(
            subscription
        )

        create_subscription_notice(
            subscription,
            notice_type=(
                SubscriptionNotice.NoticeType.CANCELLATION
            ),
            title="Subscription cancellation scheduled",
            message=(
                "Your Encore subscription will remain active "
                "through the end of the current billing period."
            ),
        )

        messages.success(
            request,
            (
                "Cancellation scheduled. Encore remains active "
                "through the end of your current billing period."
            ),
        )

    return redirect(
        "billing:studio_subscription",
        studio_slug=studio.slug,
    )


@login_required
def mark_subscription_notice_read(
    request,
    studio_slug,
    notice_id,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if not _require_admin(
        request.user,
        studio,
    ):
        return HttpResponse(
            status=403,
        )

    notice = get_object_or_404(
        SubscriptionNotice,
        pk=notice_id,
        studio=studio,
    )

    notice.is_read = True
    notice.save(
        update_fields=[
            "is_read",
        ]
    )

    return redirect(
        "billing:studio_subscription",
        studio_slug=studio.slug,
    )


@login_required
def stripe_activation_page(request, studio_slug):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if not _require_admin(request.user, studio):
        return render(request, 'dashboard/access_denied.html', {'studio': studio}, status=403)
    subscription = get_object_or_404(StudioSubscription, studio=studio)
    from .stripe_activation import account_readiness
    try:
        status = account_readiness(subscription)
        if status['ready']:
            from .stripe_activation_notifications import notify_payments_activated
            notify_payments_activated(subscription, status)
    except (ValueError, stripe.error.StripeError, AttributeError) as exc:
        status = {'mode': stripe_mode(), 'account_id': '', 'ready': False,
                  'state': 'error', 'state_label': 'Status unavailable',
                  'message': 'Unable to retrieve payment verification: ' + str(exc), 'requirements': []}
    return render(request, 'billing/stripe_activation.html', {
        'studio': studio, 'role': 'administrator', 'subscription': subscription,
        'connect_status': status, 'stripe_publishable_key': settings.STRIPE_PUBLISHABLE_KEY,
        'settings_section': 'subscription',
    })


@login_required
def stripe_activation_session(request, studio_slug):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if not _require_admin(request.user, studio):
        return JsonResponse({'error': 'Access denied'}, status=403)
    subscription = get_object_or_404(StudioSubscription, studio=studio)
    from .stripe_activation import create_activation_session
    try:
        return JsonResponse({'client_secret': create_activation_session(subscription)})
    except (ValueError, stripe.error.StripeError, AttributeError) as exc:
        logging.getLogger(__name__).warning('Connect Account Session failed for studio %s: %s', studio.pk, exc)
        return JsonResponse({'error': 'Stripe could not start embedded verification: ' + str(exc)}, status=400)


@login_required
def stripe_activation_status(request, studio_slug):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if not _require_admin(request.user, studio):
        return JsonResponse({'error': 'Access denied'}, status=403)
    subscription = get_object_or_404(StudioSubscription, studio=studio)
    from .stripe_activation import account_readiness
    try:
        status = account_readiness(subscription)
        if status['ready']:
            from .stripe_activation_notifications import notify_payments_activated
            notify_payments_activated(subscription, status)
        return JsonResponse(status)
    except (ValueError, stripe.error.StripeError, AttributeError):
        return JsonResponse({'error': 'Stripe verification status could not be loaded.'}, status=502)


@login_required
def stripe_connect_start(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if not _require_admin(
        request.user,
        studio,
    ):
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    subscription = get_object_or_404(
        StudioSubscription,
        studio=studio,
    )

    try:
        account_link = create_account_link(
            request,
            subscription,
            owner_email=request.user.email,
        )
    except (stripe.error.StripeError, ValueError) as exc:
        messages.error(
            request,
            (
                "Stripe could not start payment onboarding. "
                f"{str(exc)}"
            ),
        )
        return redirect(
            "billing:studio_subscription",
            studio_slug=studio.slug,
        )

    return redirect(
        account_link.url
    )


@login_required
def stripe_connect_refresh(
    request,
    studio_slug,
):
    return stripe_connect_start(
        request,
        studio_slug,
    )


@login_required
def stripe_connect_return(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if not _require_admin(
        request.user,
        studio,
    ):
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    subscription = get_object_or_404(
        StudioSubscription,
        studio=studio,
    )

    try:
        sync_connected_account(
            subscription
        )
        subscription.refresh_from_db()

        if subscription.payments_connected:
            messages.success(
                request,
                (
                    "Stripe payments are connected. "
                    "Online registration payments can now be "
                    "processed for this studio."
                ),
            )
        else:
            messages.info(
                request,
                (
                    "Stripe saved the onboarding progress, but "
                    "additional information is still required "
                    "before payments can be accepted."
                ),
            )
    except stripe.error.StripeError:
        messages.error(
            request,
            (
                "Encore could not verify the Stripe account yet. "
                "Try the connection again."
            ),
        )

    return redirect(
        "billing:stripe_activation_page",
        studio_slug=studio.slug,
    )


@csrf_exempt
def stripe_connect_webhook(
    request,
):
    secret = getattr(
        settings,
        "STRIPE_CONNECT_WEBHOOK_SECRET",
        "",
    )

    if not secret:
        return HttpResponse(
            status=400,
        )

    payload = request.body
    signature = request.META.get(
        "HTTP_STRIPE_SIGNATURE",
        "",
    )

    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=signature,
            secret=secret,
        )
    except (
        ValueError,
        stripe.error.SignatureVerificationError,
    ):
        return HttpResponse(
            status=400,
        )

    event_type = event["type"]
    obj = event["data"]["object"]
    connected_account_id = event.get(
        "account",
        "",
    )

    if event_type in {"refund.created", "refund.updated", "refund.failed"}:
        try:
            from .refund_services import reconcile_from_webhook
            reconcile_from_webhook(obj, connected_account_id)
        except Exception:
            logging.getLogger(__name__).exception("Refund webhook reconciliation failed")
            return HttpResponse(status=500)

    if event_type == "account.updated":
        account_id = stripe_value(
            obj,
            "id",
            connected_account_id,
        )

        subscription = (
            subscription_for_connected_account(
                account_id
            )
        )

        if subscription and stripe_mode() == "live":
            subscription.stripe_connect_details_submitted = bool(
                stripe_value(
                    obj,
                    "details_submitted",
                    False,
                )
            )
            subscription.stripe_connect_charges_enabled = bool(
                stripe_value(
                    obj,
                    "charges_enabled",
                    False,
                )
            )
            subscription.stripe_connect_payouts_enabled = bool(
                stripe_value(
                    obj,
                    "payouts_enabled",
                    False,
                )
            )
            subscription.payments_connected = (
                subscription.stripe_connect_details_submitted
                and subscription.stripe_connect_charges_enabled
                and subscription.stripe_connect_payouts_enabled
            )
            subscription.save(
                update_fields=[
                    "stripe_connect_details_submitted",
                    "stripe_connect_charges_enabled",
                    "stripe_connect_payouts_enabled",
                    "payments_connected",
                    "updated_at",
                ]
            )

    elif event_type in {"payment_intent.processing", "payment_intent.payment_failed"}:
        from .autopay_services import update_autopay_attempt_from_intent
        if stripe_metadata(obj).get("autopay_charge_id"):
            try:
                update_autopay_attempt_from_intent(obj, connected_account_id)
            except Exception:
                logging.getLogger(__name__).exception("Unable to update AutoPay processing/failure status")
                return HttpResponse(status=500)

    elif event_type == "payment_intent.succeeded":
        metadata = stripe_metadata(obj)
        if metadata.get("autopay_charge_id"):
            from .autopay_services import update_autopay_attempt_from_intent
            try:
                updated = update_autopay_attempt_from_intent(obj, connected_account_id)
                if updated is None:
                    logging.getLogger(__name__).error("Unmatched automatic tuition payment event %s", stripe_value(obj, "id"))
                    return HttpResponse(status=500)
            except Exception:
                logging.getLogger(__name__).exception("Unable to reconcile completed automatic tuition payment")
                return HttpResponse(status=500)
            return HttpResponse(status=200)

        if metadata.get("encore_kind") == FAMILY_BALANCE_PAYMENT_KIND:
            try:
                finalize_family_balance_payment(
                    obj,
                    connected_account_id=connected_account_id,
                )
            except Exception:
                logging.getLogger(__name__).exception(
                    "Unable to finalize Encore family balance payment from Stripe webhook."
                )
        else:
            try:
                from registration_portal.payment_services import (
                    finalize_from_connect_webhook,
                )

                finalize_from_connect_webhook(
                    obj,
                    connected_account_id=connected_account_id,
                )
            except Exception:
                logging.getLogger(__name__).exception(
                    "Unable to finalize Encore registration from Stripe webhook."
                )

    return HttpResponse(
        status=200,
    )


def _subscription_for_stripe_id(
    stripe_subscription_id,
):
    return (
        StudioSubscription.objects
        .filter(
            stripe_subscription_id=(
                stripe_subscription_id
            )
        )
        .select_related(
            "studio",
        )
        .first()
    )


@csrf_exempt
def stripe_webhook(request):
    payload = request.body

    signature = request.META.get(
        "HTTP_STRIPE_SIGNATURE",
        "",
    )

    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=signature,
            secret=(
                settings.STRIPE_WEBHOOK_SECRET
            ),
        )
    except (
        ValueError,
        stripe.error.SignatureVerificationError,
    ):
        return HttpResponse(
            status=400,
        )

    event_type = event[
        "type"
    ]

    obj = event[
        "data"
    ]["object"]

    if (
        event_type
        == "checkout.session.completed"
    ):
        intent_id = stripe_metadata(
            obj
        ).get(
            "encore_signup_intent_id"
        )

        if intent_id:
            intent = (
                StudioSignupIntent.objects
                .filter(
                    pk=intent_id,
                )
                .first()
            )

            if intent:
                from .subscription_services import (
                    finalize_paid_signup,
                )

                try:
                    finalize_paid_signup(
                        intent,
                        obj,
                    )
                except Exception:
                    pass

    elif event_type == "invoice.payment_failed":
        stripe_subscription_id = stripe_value(
            obj,
            "subscription",
        )

        subscription = _subscription_for_stripe_id(
            stripe_subscription_id
        )

        if subscription:
            grace_days = getattr(
                settings,
                "ENCORE_SUBSCRIPTION_GRACE_DAYS",
                7,
            )

            subscription.status = (
                StudioSubscription.Status.GRACE
            )

            subscription.grace_period_ends_at = (
                timezone.now()
                + timedelta(
                    days=grace_days
                )
            )

            subscription.save(
                update_fields=[
                    "status",
                    "grace_period_ends_at",
                    "updated_at",
                ]
            )

            message = (
                "We could not process your Encore subscription "
                f"payment. Your studio remains available during "
                f"a {grace_days}-day grace period while Stripe "
                "retries the payment."
            )

            create_subscription_notice(
                subscription,
                notice_type=(
                    SubscriptionNotice.NoticeType.PAYMENT_FAILED
                ),
                title="Subscription payment failed",
                message=message,
            )

            send_subscription_email(
                subscription.studio,
                subject=(
                    "Action needed: Encore payment failed"
                ),
                message=message,
            )

    elif event_type == "invoice.payment_succeeded":
        stripe_subscription_id = stripe_value(
            obj,
            "subscription",
        )

        subscription = _subscription_for_stripe_id(
            stripe_subscription_id
        )

        if subscription:
            was_problem = (
                subscription.status
                in {
                    StudioSubscription.Status.PAST_DUE,
                    StudioSubscription.Status.GRACE,
                }
            )

            subscription.status = (
                StudioSubscription.Status.ACTIVE
            )

            subscription.grace_period_ends_at = None

            subscription.save(
                update_fields=[
                    "status",
                    "grace_period_ends_at",
                    "updated_at",
                ]
            )

            if not subscription.studio.is_active:
                subscription.studio.is_active = True
                subscription.studio.save(
                    update_fields=[
                        "is_active",
                        "updated_at",
                    ]
                )

            billing_reason = stripe_value(
                obj,
                "billing_reason",
                "",
            )

            if (
                billing_reason
                == "subscription_cycle"
            ):
                apply_renewal_state(
                    subscription
                )

            if was_problem:
                create_subscription_notice(
                    subscription,
                    notice_type=(
                        SubscriptionNotice.NoticeType.PAYMENT_RECOVERED
                    ),
                    title="Subscription payment recovered",
                    message=(
                        "Your Encore subscription payment "
                        "was successfully processed."
                    ),
                )

    elif event_type in {
        "customer.subscription.updated",
        "customer.subscription.deleted",
    }:
        stripe_subscription_id = obj[
            "id"
        ]

        subscription = _subscription_for_stripe_id(
            stripe_subscription_id
        )

        if subscription:
            if (
                event_type
                == "customer.subscription.deleted"
            ):
                subscription.status = (
                    StudioSubscription.Status.CANCELLED
                )

                subscription.studio.is_active = False

                subscription.studio.save(
                    update_fields=[
                        "is_active",
                        "updated_at",
                    ]
                )

            else:
                stripe_status = stripe_value(
                    obj,
                    "status",
                    "",
                )

                status_map = {
                    "active": (
                        StudioSubscription.Status.ACTIVE
                    ),
                    "past_due": (
                        StudioSubscription.Status.PAST_DUE
                    ),
                    "incomplete": (
                        StudioSubscription.Status.INCOMPLETE
                    ),
                    "canceled": (
                        StudioSubscription.Status.CANCELLED
                    ),
                }

                if stripe_status in status_map:
                    subscription.status = (
                        status_map[
                            stripe_status
                        ]
                    )

                subscription.cancel_at_period_end = bool(
                    stripe_value(
                        obj,
                        "cancel_at_period_end",
                        False,
                    )
                )

            subscription.save()

    return HttpResponse(
        status=200,
    )


@login_required
def resume_studio_subscription(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if not _require_admin(
        request.user,
        studio,
    ):
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    if request.method != "POST":
        return redirect(
            "billing:studio_subscription",
            studio_slug=studio.slug,
        )

    subscription = get_object_or_404(
        StudioSubscription,
        studio=studio,
    )

    if subscription.cancel_at_period_end:
        resume_subscription(
            subscription
        )

        create_subscription_notice(
            subscription,
            notice_type=(
                SubscriptionNotice.NoticeType.CANCELLATION
            ),
            title="Cancellation removed",
            message=(
                "Your Encore subscription will continue normally "
                "and renew on its regular billing date."
            ),
        )

        messages.success(
            request,
            (
                "Cancellation removed. Your Encore subscription "
                "will continue normally."
            ),
        )
    else:
        messages.info(
            request,
            "Your subscription is already set to continue.",
        )

    return redirect(
        "billing:studio_subscription",
        studio_slug=studio.slug,
    )


def _family_guardian_for_request(request, studio):
    return (
        Guardian.objects
        .filter(
            family__studio=studio,
            user=request.user,
            is_active=True,
        )
        .select_related("family", "user")
        .order_by("-is_primary", "pk")
        .first()
    )


def _family_account_for_guardian(studio, guardian):
    if guardian is None:
        return None

    return (
        FamilyAccount.objects
        .filter(
            studio=studio,
            family=guardian.family,
            is_active=True,
        )
        .first()
    )


@login_required
def family_payment_intent(request, studio_slug):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if request.method != "POST":
        return JsonResponse({"error": "POST required."}, status=405)

    guardian = _family_guardian_for_request(request, studio)
    if guardian is None:
        return JsonResponse({"error": "Family access denied."}, status=403)

    account = _family_account_for_guardian(studio, guardian)
    if account is None:
        return JsonResponse({"error": "No active family billing account was found."}, status=404)

    try:
        subscription = studio.subscription
    except StudioSubscription.DoesNotExist:
        return JsonResponse({"error": "Online payments are not configured for this studio."}, status=400)

    receipt_email = (
        getattr(guardian.user, "email", "")
        or getattr(guardian.family, "primary_email", "")
        or ""
    )

    try:
        result = create_family_balance_payment_intent(
            account=account,
            subscription=subscription,
            receipt_email=receipt_email,
        )
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except stripe.error.StripeError:
        logging.getLogger(__name__).exception(
            "Unable to create family balance PaymentIntent for studio %s",
            studio.pk,
        )
        return JsonResponse(
            {"error": "Stripe could not start the payment. Please try again."},
            status=502,
        )

    return JsonResponse(
        {
            "client_secret": result["client_secret"],
            "amount": f"{result['amount_due']:.2f}",
        }
    )


@login_required
def family_payment_return(request, studio_slug):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    guardian = _family_guardian_for_request(request, studio)
    if guardian is None:
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    payment_intent_id = str(
        request.GET.get("payment_intent", "") or ""
    ).strip()

    if not payment_intent_id:
        messages.error(request, "Encore could not identify the completed payment.")
        return redirect("billing:family_payments", studio_slug=studio.slug)

    try:
        subscription = studio.subscription
    except StudioSubscription.DoesNotExist:
        subscription = None

    if not subscription:
        messages.error(request, "The studio payment account is not available.")
        return redirect("billing:family_payments", studio_slug=studio.slug)

    try:
        connect_id = connected_account_for_subscription(subscription)
        configure_stripe()
        payment_intent = stripe.PaymentIntent.retrieve(
            payment_intent_id,
            stripe_account=connect_id,
        )
        metadata = stripe_metadata(payment_intent)
        family_account = _family_account_for_guardian(studio, guardian)
        if family_account is None or str(metadata.get("family_account_id", "")) != str(family_account.pk):
            messages.error(request, "This payment does not belong to your family account.")
            return redirect("billing:family_payments", studio_slug=studio.slug)
        payment = finalize_family_balance_payment(
            payment_intent,
            connected_account_id=connect_id,
        )
    except (stripe.error.StripeError, ValueError):
        payment = None

    if payment is not None:
        messages.success(
            request,
            f"Payment received: ${payment.amount:.2f}. Your family balance has been updated.",
        )
    else:
        messages.info(
            request,
            "Your payment is still processing. Encore will update the balance when Stripe confirms it.",
        )

    return redirect("billing:family_payments", studio_slug=studio.slug)


@login_required
def cancel_family_billing(request, studio_slug):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    guardian = _family_guardian_for_request(request, studio)
    if guardian is None:
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    if request.method != "POST":
        return redirect("billing:family_payments", studio_slug=studio.slug)

    if not guardian.is_primary:
        messages.error(
            request,
            "Only the primary guardian can stop recurring family billing.",
        )
        return redirect("billing:family_payments", studio_slug=studio.slug)

    account = _family_account_for_guardian(studio, guardian)
    if account is None:
        messages.error(request, "No active family billing account was found.")
        return redirect("billing:family_payments", studio_slug=studio.slug)

    # Prevent the previous mismatch: stopping schedules while leaving students
    # actively enrolled allows billing to restart on the next enrollment save.
    messages.warning(
        request,
        "To end class tuition, request withdrawal from the studio. Your active "
        "enrollments and charges have not been changed. Disabling AutoPay "
        "only stops automatic collection; it does not cancel classes.",
    )

    return redirect("billing:family_payments", studio_slug=studio.slug)


@login_required
def family_payments(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    guardian = _family_guardian_for_request(request, studio)

    if guardian is None:
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    account = _family_account_for_guardian(studio, guardian)

    charges = []
    payments = []
    credits = []

    if account is not None:
        charges = list(
            account.charges
            .select_related(
                "student",
                "class_instance",
            )
            .order_by("-created_at")[:30]
        )

        payments = list(
            account.payments
            .order_by("-paid_at")[:30]
        )

        credits = list(
            account.credits
            .filter(is_void=False)
            .select_related("student")
            .order_by("-created_at")[:20]
        )

    try:
        subscription = studio.subscription
    except StudioSubscription.DoesNotExist:
        subscription = None

    payment_setup_message = ""
    connected_account_id = ""
    if subscription:
        try:
            candidate_id = connected_account_for_subscription(subscription)
            # Checking only that an ID exists can show a payment form before
            # the corresponding test/live Connect account has enabled charges.
            verify_connected_account(candidate_id)
            connected_account_id = candidate_id
        except ValueError as exc:
            payment_setup_message = str(exc)
        except stripe.error.StripeError:
            logging.getLogger(__name__).exception(
                "Could not validate Stripe Connect readiness for studio %s", studio.pk
            )
            payment_setup_message = (
                "Stripe could not verify this studio's payment account. "
                "Please try again shortly or contact the studio."
            )
    else:
        payment_setup_message = "The studio has not set up Stripe payments."
    online_payments_enabled = bool(connected_account_id)

    amount_due = (
        max(account.balance, Decimal("0.00"))
        if account is not None
        else Decimal("0.00")
    )
    open_charge_count = (
        account.charges.filter(
            status__in=[
                Charge.Status.OPEN,
                Charge.Status.PARTIALLY_PAID,
            ]
        ).count()
        if account is not None
        else 0
    )
    active_recurring_count = (
        account.recurring_schedules.filter(is_active=True).count()
        if account is not None
        else 0
    )

    # A past-due schedule is not the family's NEXT billing date.  Never
    # present a historical charge date as an upcoming payment commitment.
    next_billing_date = (
        account.recurring_schedules.filter(
            is_active=True, next_charge_date__gte=timezone.localdate()
        ).order_by("next_charge_date").values_list("next_charge_date", flat=True).first()
        if account else None
    )
    outstanding_pending = False
    # An ACH debit can take several business days to settle. This banner is
    # informational, not a statement that the balance is paid.
    if account and subscription and connected_account_id:
        from .models import FamilyAutoPayAttempt
        outstanding_pending = FamilyAutoPayAttempt.objects.filter(
            profile__account=account, profile__connected_account_id=connected_account_id,
            status__in=["submitted", "processing", "requires_action", "requires_confirmation"],
        ).exists()

    stripe_publishable_key = getattr(settings, "STRIPE_PUBLISHABLE_KEY", "")

    context = {
        "studio": studio,
        "role": "family",
        "account": account,
        "charges": charges,
        "payments": payments,
        "credits": credits,
        "subscription": subscription,
        "online_payments_enabled": online_payments_enabled,
        "amount_due": amount_due,
        "open_charge_count": open_charge_count,
        "active_recurring_count": active_recurring_count,
        "next_billing_date": next_billing_date,
        "outstanding_pending": outstanding_pending,
        "can_pay_online": bool(
            online_payments_enabled
            and amount_due > Decimal("0.00")
            and subscription
            and connected_account_id
            and stripe_publishable_key
        ),
        "stripe_publishable_key": stripe_publishable_key,
        "stripe_connected_account_id": connected_account_id,
        "payment_setup_message": payment_setup_message,
        "autopay_profile": (current_profile(account, subscription) if account and subscription and connected_account_id else None),
    }
    context.update(
        parent_portal_context(
            request,
            studio,
            section="payments",
        )
    )

    return render(
        request,
        "billing/parent_payments.html",
        context,
    )


@login_required
def family_autopay_setup(request, studio_slug):
    """POST: request a verified bank/card SetupIntent with recorded consent."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    guardian = _family_guardian_for_request(request, studio)
    if not guardian or not guardian.is_primary:
        return JsonResponse({"error": "Only the primary guardian can enable AutoPay."}, status=403)
    account = _family_account_for_guardian(studio, guardian)
    if not account:
        return JsonResponse({"error": "No billing account."}, status=404)
    import json
    try:
        payload = json.loads(request.body or b"{}")
        if payload.get("autopay_consent") is not True:
            raise ValueError("Please authorize future recurring tuition payments first.")
        method_type = str(payload.get("method_type", ""))
        if method_type not in {"card", "us_bank_account"}:
            raise ValueError("Select ACH or Card to continue.")
        result = create_setup_intent(account, studio.subscription, guardian, method_type)
        request.session[f"autopay_setup_{studio.pk}_{account.pk}"] = result["setup_intent_id"]
        # Snapshot consent to charge no more than the displayed current amount.
        # Setup is allowed without a balance; consent must not be inferred.
        request.session[f"autopay_balance_{studio.pk}_{account.pk}"] = (
            str(max(account.balance, Decimal("0.00")))
            if payload.get("collect_current_balance") is True else ""
        )
        return JsonResponse(result)
    except (ValueError, stripe.error.StripeError) as exc:
        logging.getLogger(__name__).exception("Stripe AutoPay setup failed")
        return JsonResponse({"error": str(exc) if isinstance(exc, ValueError) else "Stripe could not begin payment method setup."}, status=400)


@login_required
def family_autopay_confirm(request, studio_slug):
    """Confirm consent only after independently retrieving a successful SetupIntent."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    guardian = _family_guardian_for_request(request, studio)
    if not guardian or not guardian.is_primary:
        return JsonResponse({"error": "Only the primary guardian can enable AutoPay."}, status=403)
    account = _family_account_for_guardian(studio, guardian)
    if not account:
        return JsonResponse({"error": "No billing account."}, status=404)
    import json
    try:
        payload = json.loads(request.body or b"{}")
        intent_id = str(payload.get("setup_intent_id", ""))
        if not intent_id.startswith("seti_"):
            raise ValueError("Invalid Stripe setup reference.")
        session_key = f"autopay_setup_{studio.pk}_{account.pk}"
        if request.session.get(session_key) != intent_id:
            raise ValueError("This setup session has expired. Please start AutoPay setup again.")
        profile = activate_from_setup(account, studio.subscription, guardian, intent_id)
        request.session.pop(session_key, None)
        balance_key = f"autopay_balance_{studio.pk}_{account.pk}"
        consented_amount = request.session.pop(balance_key, "")
        collection = {"status": "not_requested"}
        if consented_amount and payload.get("collect_current_balance") is True:
            from decimal import Decimal as _Decimal
            profile._activation_balance_authorized = _Decimal(consented_amount)
            try:
                collection = collect_activation_balance_once(account, studio.subscription, profile)
            except stripe.error.StripeError as exc:
                logging.getLogger(__name__).exception(
                    "AutoPay initial balance collection REJECTED by Stripe for studio=%s family_account=%s connect=%s code=%s request_id=%s",
                    studio.pk, account.pk, profile.connected_account_id,
                    getattr(exc, "code", None), getattr(exc, "request_id", None),
                )
                collection = {"status": "failed_to_start", "reason": "stripe_rejected",
                    "request_id": getattr(exc, "request_id", "") or ""}
            except ValueError as exc:
                logging.getLogger(__name__).warning(
                    "AutoPay initial balance collection validation failed for family_account=%s: %s",
                    account.pk, exc,
                )
                collection = {"status": "failed_to_start", "reason": "validation", "message": str(exc)}
        status = collection.get("status", "")
        if status == "succeeded":
            messages.success(request, "AutoPay is enabled and your existing balance payment was received.")
        elif status in {"processing", "requires_action", "requires_confirmation", "already_pending"}:
            messages.info(request, "AutoPay is enabled. Your existing balance payment is pending Stripe confirmation; ACH may take several business days.")
        elif status == "failed_to_start":
            messages.warning(request, "AutoPay is enabled, but Stripe did not start the existing balance payment. Your balance is still due. Please contact the studio before retrying so you are not charged twice.")
        else:
            messages.success(request, "AutoPay is enabled. Future tuition will be collected automatically on its scheduled due dates.")
        return JsonResponse({"enabled": profile.is_enabled, "payment_method": f"{profile.card_brand} •••• {profile.card_last4}", "balance_collection": collection})
    except (ValueError, stripe.error.StripeError, json.JSONDecodeError) as exc:
        return JsonResponse({"error": str(exc) if isinstance(exc, ValueError) else "Unable to verify the saved payment method."}, status=400)


@login_required
def family_autopay_disable(request, studio_slug):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    guardian = _family_guardian_for_request(request, studio)
    if not guardian or not guardian.is_primary:
        return JsonResponse({"error": "Only the primary guardian can disable AutoPay."}, status=403)
    account = _family_account_for_guardian(studio, guardian)
    if not account:
        return JsonResponse({"error": "No billing account."}, status=404)
    disable_autopay(account, studio.subscription)
    messages.success(request, "AutoPay is disabled. Your class enrollment and monthly billing remain active.")
    return redirect("billing:family_payments", studio_slug=studio.slug)


@login_required
def family_withdrawal_request(request, studio_slug):
    """Primary guardian requests withdrawal; enrollment/billing untouched pending review."""
    from enrollments.models import Enrollment
    from .models import FamilyWithdrawalRequest
    studio=get_object_or_404(Studio,slug=studio_slug,is_active=True)
    guardian=_family_guardian_for_request(request,studio)
    if not guardian or not guardian.is_primary:
        return render(request,"dashboard/access_denied.html",{"studio":studio},status=403)
    account=_family_account_for_guardian(studio,guardian)
    if account is None:return redirect("billing:family_payments",studio_slug=studio_slug)
    eligible=Enrollment.objects.filter(student__family=account.family,student__studio=studio,
        class_instance__studio=studio,status=Enrollment.Status.ACTIVE).select_related("student","class_instance")
    if request.method=="POST":
        raw_id=str(request.POST.get("enrollment_id", ""))
        enrollment=eligible.filter(pk=int(raw_id)).first() if raw_id.isdigit() else None
        if enrollment is None:
            messages.error(request,"Select one of your family's active classes.")
        elif FamilyWithdrawalRequest.objects.filter(account=account,enrollment=enrollment,status="pending").exists():
            messages.info(request,"A withdrawal request is already awaiting studio review for this class.")
        else:
            FamilyWithdrawalRequest.objects.create(account=account,enrollment=enrollment,requested_by=request.user,
                reason=request.POST.get("reason","").strip()[:1500])
            messages.success(request,"Withdrawal requested. Enrollment and future tuition remain active until the studio approves it.")
        return redirect("billing:family_withdrawal_request",studio_slug=studio_slug)
    return render(request,"billing/family_withdrawal.html",{
        **parent_portal_context(request,studio,section="payments"),
        "studio":studio,"role":"family","enrollments":eligible,
        "requests":FamilyWithdrawalRequest.objects.filter(account=account).select_related("enrollment__student","enrollment__class_instance")[:25]})


@login_required
def studio_billing_reviews(request, studio_slug):
    from .models import FamilyWithdrawalRequest, FamilyBillingHold
    from enrollments.models import Enrollment
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if not _require_admin(request.user, studio):
        return render(request, "dashboard/access_denied.html", {"studio": studio}, status=403)
    holds = list(FamilyBillingHold.objects.filter(account__studio=studio)
        .exclude(status="released").select_related("account__family", "account__studio"))
    for hold in holds:
        hold.active_enrollments = list(Enrollment.objects.filter(
            student__family_id=hold.account.family_id, student__studio=studio,
            class_instance__studio=studio, status=Enrollment.Status.ACTIVE)
            .select_related("student", "class_instance").order_by("student__last_name", "class_instance__name"))
    return render(request, "billing/billing_reviews.html", {
        "studio": studio, "role": "administrator",
        "withdrawals": FamilyWithdrawalRequest.objects.filter(account__studio=studio,status="pending")
            .select_related("account__family", "enrollment__student", "enrollment__class_instance"),
        "holds": holds,
    })


@login_required
def studio_withdrawal_decision(request,studio_slug,request_id):
    from .models import FamilyWithdrawalRequest
    from enrollments.models import Enrollment
    from django.db import transaction
    studio=get_object_or_404(Studio,slug=studio_slug,is_active=True)
    if not _require_admin(request.user,studio):return HttpResponse(status=403)
    if request.method!="POST":return HttpResponse(status=405)
    decision=request.POST.get("decision")
    if decision not in ("approve","reject"):return HttpResponse(status=400)
    with transaction.atomic():
        withdrawal=get_object_or_404(FamilyWithdrawalRequest.objects.select_for_update(),pk=request_id,account__studio=studio)
        if withdrawal.status!="pending":
            messages.info(request,"This withdrawal has already been reviewed.")
        else:
            enrollment=Enrollment.objects.select_for_update().get(pk=withdrawal.enrollment_id)
            if decision=="approve" and enrollment.status==Enrollment.Status.ACTIVE:
                from performance.services import archive_withdrawn_enrollment
                archive_withdrawn_enrollment(enrollment, reason="parent_withdrawal")
                enrollment.status=Enrollment.Status.DROPPED
                enrollment.dropped_at=timezone.now()
                enrollment.save(update_fields=["status","dropped_at","updated_at"])
                # billing.signals post_save synchronizes enrollment and studio-wide schedules.
            withdrawal.status="approved" if decision=="approve" else "rejected"
            withdrawal.reviewed_by=request.user
            withdrawal.reviewed_at=timezone.now()
            withdrawal.save(update_fields=["status","reviewed_by","reviewed_at"])
            messages.success(request,"Withdrawal decision saved. Existing charges remain due.")
    return redirect("billing:studio_billing_reviews",studio_slug=studio_slug)


@login_required
def studio_hold_decision(request, studio_slug, account_id):
    """Administrator review, or explicitly selected nonpayment class removals."""
    from django.db import transaction
    from enrollments.models import Enrollment
    from .models import FamilyBillingHold, FamilyAutoPayAttempt
    from .nonpayment_removal import notify_nonpayment_removal
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if not _require_admin(request.user, studio):
        return HttpResponse(status=403)
    if request.method != "POST":
        return HttpResponse(status=405)
    decision = request.POST.get("decision")
    if decision not in ("retain", "release", "remove"):
        return HttpResponse(status=400)
    with transaction.atomic():
        hold = get_object_or_404(FamilyBillingHold.objects.select_for_update()
            .select_related("account"), account_id=account_id, account__studio=studio)
        if decision == "remove":
            if (request.POST.get("confirm_removal") != "yes"
                    or request.POST.get("verify_payment") != "yes"):
                messages.error(request, "Confirm the removal and verify there are no outstanding ACH payments processing.")
                return redirect("billing:studio_billing_reviews", studio_slug=studio.slug)
            ids = {int(v) for v in request.POST.getlist("enrollment_ids") if v.isdigit()}
            if not ids:
                messages.error(request, "Select the specific class enrollments to remove.")
                return redirect("billing:studio_billing_reviews", studio_slug=studio.slug)
            if hold.account.balance <= Decimal("0.00"):
                messages.error(request, "The balance is paid; no nonpayment removal is permitted.")
                return redirect("billing:studio_billing_reviews", studio_slug=studio.slug)
            if FamilyAutoPayAttempt.objects.filter(profile__account=hold.account,
                status__in=["submitted", "processing", "requires_action", "requires_confirmation"]).exists():
                messages.error(request, "A tuition payment is processing. Verify settlement before removal.")
                return redirect("billing:studio_billing_reviews", studio_slug=studio.slug)
            rows = list(Enrollment.objects.select_for_update().filter(
                pk__in=ids, student__family_id=hold.account.family_id,
                student__studio=studio, class_instance__studio=studio,
                status=Enrollment.Status.ACTIVE).select_related(
                "student", "class_instance__instructor__user", "class_instance__assistant_instructor__user"))
            if len(rows) != len(ids):
                messages.error(request, "Some selected enrollments are no longer eligible. Refresh and retry.")
                return redirect("billing:studio_billing_reviews", studio_slug=studio.slug)
            timestamp = timezone.now()
            from performance.services import archive_withdrawn_enrollment
            for enrollment in rows:
                archive_withdrawn_enrollment(enrollment, reason="nonpayment")
                enrollment.status = Enrollment.Status.DROPPED
                enrollment.dropped_at = timestamp
                enrollment.notes = (enrollment.notes + "\n" if enrollment.notes else "") + (
                    f"[{timestamp.isoformat()}] Administrator nonpayment removal by user #{request.user.pk}. "
                    f"Family account #{hold.account_id}; prior financial and attendance records preserved.")
                enrollment.save(update_fields=["status", "dropped_at", "notes", "updated_at"])
            from .models import FamilyBillingAction
            FamilyBillingAction.objects.create(account=hold.account, performed_by=request.user,
                action="remove", reason="Administrator confirmed removal for unpaid tuition.",
                details={"enrollment_ids": [e.pk for e in rows],
                         "students": [e.student_id for e in rows],
                         "classes": [e.class_instance_id for e in rows]})
            hold.status = "released"
            hold.reason = f"Administrator removed {len(rows)} selected class enrollment(s) due to unpaid tuition."
            hold.reviewed_by = request.user
            hold.reviewed_at = timestamp
            hold.save(update_fields=["status", "reason", "reviewed_by", "reviewed_at", "updated_at"])
            # Send only after the enrollment transaction has committed.
            transaction.on_commit(lambda: notify_nonpayment_removal(
                studio=studio, account=hold.account, removals=rows, administrator_id=request.user.pk))
            messages.success(request, f"Removed {len(rows)} selected enrollment(s). Prior records are unchanged; notices are being sent.")
        else:
            hold.status = "active" if decision == "retain" else "released"
            hold.reason = "Administrator retained enrollment for review." if decision == "retain" else "Review flag cleared by administrator."
            hold.reviewed_by = request.user
            hold.reviewed_at = timezone.now()
            hold.save(update_fields=["status", "reason", "reviewed_by", "reviewed_at", "updated_at"])
            messages.success(request, "Review decision saved; no enrollments were changed.")
    return redirect("billing:studio_billing_reviews", studio_slug=studio.slug)


@login_required
def studio_overdue_account(request, studio_slug, account_id):
    from .models import FamilyBillingHold, FamilyAutoPayAttempt, FamilyBillingAction
    from enrollments.models import Enrollment
    from datetime import timedelta
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if not _require_admin(request.user, studio):
        return HttpResponse(status=403)
    account = _account_for_studio(studio, account_id)
    charges = list(account.charges.exclude(status__in=[Charge.Status.VOID, Charge.Status.DRAFT])
        .select_related("student", "recurring_schedule__tuition_plan").order_by("due_date", "pk"))
    settings_obj = StudioTuitionSettings.objects.filter(studio=studio).first()
    for charge in charges:
        policy = (charge.recurring_schedule.tuition_plan if charge.recurring_schedule_id else
                  settings_obj.default_tuition_plan if settings_obj else None)
        days = (policy.grace_period_days if policy.grace_period_enabled else 0) if policy else 7
        charge.review_deadline = charge.due_date + timedelta(days=days) if charge.due_date else None
    return render(request, "billing/overdue_account_detail.html", {
        "studio": studio, "role": "administrator", "account": account,
        "charges": charges, "hold": FamilyBillingHold.objects.filter(account=account).first(),
        "enrollments": Enrollment.objects.filter(student__family=account.family,
            class_instance__studio=studio, status=Enrollment.Status.ACTIVE)
            .select_related("student", "class_instance").order_by("student__last_name", "class_instance__name"),
        "attempts": FamilyAutoPayAttempt.objects.filter(profile__account=account)
            .select_related("charge").order_by("-created_at")[:20],
        "payments": account.payments.order_by("-created_at")[:20],
        "actions": FamilyBillingAction.objects.filter(account=account)
            .select_related("performed_by", "charge")[:30],
        "pending_payment": FamilyAutoPayAttempt.objects.filter(profile__account=account,
            status__in=["pending", "submitted", "processing", "requires_action", "requires_confirmation"]).exists(),
    })


@login_required
def studio_overdue_account_action(request, studio_slug, account_id):
    from datetime import date
    from django.db import transaction
    from .models import FamilyBillingHold, FamilyBillingAction, Credit, CreditAllocation, FamilyAutoPayAttempt
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if not _require_admin(request.user, studio):
        return HttpResponse(status=403)
    if request.method != "POST":
        return HttpResponse(status=405)
    account = _account_for_studio(studio, account_id)
    action = request.POST.get("action", "")
    reason = request.POST.get("reason", "").strip()
    url = "billing:studio_overdue_account"
    if action not in {"extend", "excuse", "defer", "retain", "release"} or not reason:
        messages.error(request, "Choose a valid action and enter a reason.")
        return redirect(url, studio_slug=studio_slug, account_id=account_id)
    with transaction.atomic():
        hold = FamilyBillingHold.objects.select_for_update().filter(account=account).first()
        charge = None
        details = {}
        if action in {"extend", "excuse"}:
            charge_id = request.POST.get("charge_id", "")
            charge = Charge.objects.select_for_update().filter(pk=charge_id, account=account,
                status__in=[Charge.Status.OPEN, Charge.Status.PARTIALLY_PAID]).first() if charge_id.isdigit() else None
            if not charge or charge.balance_remaining <= Decimal("0"):
                messages.error(request, "Select an unpaid charge.")
                return redirect(url, studio_slug=studio_slug, account_id=account_id)
            pending = FamilyAutoPayAttempt.objects.filter(charge=charge,
                status__in=["pending", "submitted", "processing", "requires_action", "requires_confirmation"]).exists()
            if action == "extend":
                try:
                    next_date = date.fromisoformat(request.POST.get("new_due_date", ""))
                except ValueError:
                    next_date = None
                if not next_date or next_date <= timezone.localdate() or (charge.due_date and next_date <= charge.due_date):
                    messages.error(request, "Enter a future due date later than the original due date.")
                    return redirect(url, studio_slug=studio_slug, account_id=account_id)
                details = {"old_due_date": str(charge.due_date), "new_due_date": str(next_date)}
                charge.due_date = next_date
                charge.save(update_fields=["due_date", "updated_at"])
                # Future notices are recalculated from the extended deadline; existing deliveries remain audit evidence.
                if hold and hold.status != "released":
                    hold.status = "released"
                    hold.reason = "Charge deadline extended; overdue review deferred pending reevaluation."
                    hold.reviewed_by = request.user
                    hold.reviewed_at = timezone.now()
                    hold.save(update_fields=["status", "reason", "reviewed_by", "reviewed_at", "updated_at"])
            else:
                if pending:
                    messages.error(request, "A payment is processing for this charge; reconcile it before granting a credit.")
                    return redirect(url, studio_slug=studio_slug, account_id=account_id)
                try:
                    amount = Decimal(request.POST.get("amount", "")).quantize(Decimal("0.01"))
                except Exception:
                    amount = Decimal("0")
                if amount <= 0 or amount > charge.balance_remaining:
                    messages.error(request, "Excused amount must be positive and no more than this charge's unpaid balance.")
                    return redirect(url, studio_slug=studio_slug, account_id=account_id)
                credit = Credit.objects.create(account=account, student=charge.student,
                    credit_type=Credit.CreditType.MANUAL,
                    description=f"Administrator excused tuition: {charge.description}"[:255],
                    amount=amount, notes=f"Account review by user #{request.user.pk}: {reason}")
                allocation = CreditAllocation(credit=credit, charge=charge, amount=amount)
                allocation.full_clean()
                allocation.save()
                charge.refresh_status_from_balance()
                details = {"amount": str(amount), "credit_id": credit.pk}
        else:
            if hold is None:
                hold = FamilyBillingHold.objects.create(account=account, status="review", reason="Manual review")
            if action == "defer":
                try:
                    until = date.fromisoformat(request.POST.get("review_date", ""))
                except ValueError:
                    until = None
                if not until or until <= timezone.localdate():
                    messages.error(request, "Enter a future review date.")
                    return redirect(url, studio_slug=studio_slug, account_id=account_id)
                details["review_date"] = str(until)
                hold.status = "active"
                hold.reason = reason
                # The processing job respects this date even if a charge remains overdue.
                hold.reviewed_at = timezone.now()
            else:
                hold.status = "active" if action == "retain" else "released"
                hold.reason = reason
                hold.reviewed_at = timezone.now()
            hold.reviewed_by = request.user
            hold.save(update_fields=["status", "reason", "reviewed_by", "reviewed_at", "updated_at"])
        FamilyBillingAction.objects.create(account=account, charge=charge, performed_by=request.user,
            action=action, reason=reason, details=details)
    messages.success(request, "Account action recorded. Previous financial records were retained.")
    return redirect(url, studio_slug=studio_slug, account_id=account_id)
