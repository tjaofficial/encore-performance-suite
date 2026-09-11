from datetime import datetime, time, timedelta
from decimal import Decimal
import logging

from urllib.parse import urlencode
import stripe
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from studios.models import Studio

from .forms import (
    CancelSubscriptionForm,
    ChargeForm,
    CreditForm,
    DrawingBoardChangeForm,
    PaymentForm,
    SubscriptionPlanChangeForm,
    TuitionPlanForm,
)
from .models import (
    FamilyAccount,
    StudioSignupIntent,
    StudioSubscription,
    SubscriptionNotice,
    TuitionPlan,
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
            "credits": credits,
            "recurring_schedules": recurring_schedules,
            "ledger_rows": ledger_rows,
        },
    )


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

    if subscription.stripe_connected_account_id:
        try:
            sync_connected_account(
                subscription
            )
            subscription.refresh_from_db()
        except stripe.error.StripeError:
            pass

    evaluate_student_band_change(
        subscription
    )

    subscription.refresh_from_db()

    student_count = studio.students.count()

    notices = (
        studio.subscription_notices
        .filter(
            is_read=False,
        )
        .order_by(
            "-created_at",
        )
    )

    plan_form = SubscriptionPlanChangeForm(
        current_plan=subscription.plan_tier,
    )

    drawing_form = DrawingBoardChangeForm(
        initial={
            "enabled": (
                subscription.drawing_board_enabled
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
            "plan_form": plan_form,
            "drawing_form": drawing_form,
            "cancel_form": cancel_form,
            "notices": notices,
            "drawing_board_price": 39,
            "settings_section": "subscription",
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
                    "Stripe will prorate the current billing period."
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
                    "The $39/month add-on was prorated "
                    "for the current billing period."
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

    if (
        subscription.payment_mode
        != StudioSubscription.PaymentMode.SOFTWARE_PAYMENTS
    ):
        messages.error(
            request,
            (
                "Switch this studio to Software + Payments "
                "before connecting a Stripe payments account."
            ),
        )
        return redirect(
            "billing:studio_subscription",
            studio_slug=studio.slug,
        )

    try:
        account_link = create_account_link(
            request,
            subscription,
            owner_email=request.user.email,
        )
    except stripe.error.StripeError as exc:
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
        "billing:studio_subscription",
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

        if subscription:
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

    elif event_type == "payment_intent.succeeded":
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
