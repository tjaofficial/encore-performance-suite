from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal
import logging
from uuid import uuid4

import stripe
from django.conf import settings
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape

from billing.models import StudioSignupIntent
from communications.email_service import send_email
from communications.models import WorkspaceNotification
from communications.notification_services import create_workspace_notification


logger = logging.getLogger(__name__)


def _public_url(path):
    base = str(
        getattr(settings, "ENCORE_PUBLIC_BASE_URL", "")
        or ("http://127.0.0.1:8000" if settings.DEBUG else "https://encoreperformancesuite.com")
    ).rstrip("/")
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{base}{path}"


def _logo_url():
    return _public_url("/static/images/logo.png")


def _format_money(value):
    try:
        return f"${Decimal(str(value)):.2f}"
    except Exception:
        return "$0.00"


def _stripe_value(resource, key, default=None):
    if resource is None:
        return default
    if isinstance(resource, dict):
        return resource.get(key, default)
    try:
        return getattr(resource, key)
    except (AttributeError, KeyError):
        pass
    try:
        return resource[key]
    except (KeyError, TypeError):
        return default


def _stripe_datetime(timestamp):
    if not timestamp:
        return None
    return datetime.fromtimestamp(timestamp, tz=dt_timezone.utc)


def _email_shell(*, eyebrow, heading, intro, body_html, button_label=None, button_url=None, footer=None):
    logo = escape(_logo_url())
    button = ""
    if button_label and button_url:
        button = f"""
            <div style="margin:28px 0 6px;">
                <a href="{escape(button_url)}" style="display:inline-block;background:#3047f4;color:#fff;text-decoration:none;font-weight:800;font-size:15px;padding:14px 22px;border-radius:10px;">
                    {escape(button_label)}
                </a>
            </div>
        """

    footer_copy = footer or (
        "Need help? Reply to this email or contact "
        "info@encoreperformancesuite.com."
    )

    return f"""
    <!doctype html>
    <html>
    <body style="margin:0;background:#f4f7ff;font-family:Arial,Helvetica,sans-serif;color:#101535;">
        <div style="padding:34px 16px;">
            <div style="max-width:640px;margin:0 auto;background:#ffffff;border:1px solid #dfe5f3;border-radius:18px;overflow:hidden;box-shadow:0 10px 28px rgba(26,38,92,.08);">
                <div style="padding:28px 34px 18px;border-bottom:1px solid #edf0f7;">
                    <img src="{logo}" alt="Encore Performance Suite" style="display:block;width:230px;max-width:75%;height:auto;">
                </div>
                <div style="padding:30px 34px 34px;">
                    <div style="color:#3047f4;font-size:11px;font-weight:900;letter-spacing:1.3px;text-transform:uppercase;margin-bottom:8px;">
                        {escape(eyebrow)}
                    </div>
                    <h1 style="font-size:28px;line-height:1.15;margin:0 0 12px;color:#0c1240;">
                        {escape(heading)}
                    </h1>
                    <p style="font-size:16px;line-height:1.65;color:#58627d;margin:0 0 22px;">
                        {escape(intro)}
                    </p>
                    {body_html}
                    {button}
                </div>
                <div style="background:#0c174a;color:#dbe3ff;padding:20px 34px;font-size:12px;line-height:1.6;">
                    {escape(footer_copy)}
                </div>
            </div>
        </div>
    </body>
    </html>
    """


def verification_is_expired(user):
    sent_at = getattr(user, "email_verification_sent_at", None)
    if not sent_at:
        return True
    max_age = int(
        getattr(
            settings,
            "ENCORE_OWNER_EMAIL_VERIFICATION_MAX_AGE_SECONDS",
            86400,
        )
    )
    return timezone.now() > sent_at + timedelta(seconds=max_age)


def _owner_user(intent):
    User = get_user_model()
    return User.objects.get(email=intent.owner_email)


def _prepare_verification_token(user, *, rotate=False):
    if rotate or not user.email_verification_token or verification_is_expired(user):
        user.email_verification_token = uuid4()
    return user.email_verification_token


def send_verification_email(intent, *, force=False):
    user = _owner_user(intent)
    if user.email_verified_at or not user.email_verification_required:
        return False

    now = timezone.now()
    cooldown = int(
        getattr(
            settings,
            "ENCORE_OWNER_VERIFICATION_RESEND_COOLDOWN_SECONDS",
            60,
        )
    )

    if force and user.email_verification_sent_at:
        earliest = user.email_verification_sent_at + timedelta(seconds=cooldown)
        if now < earliest:
            remaining = max(1, int((earliest - now).total_seconds()))
            raise ValueError(
                f"A verification email was just sent. Please wait {remaining} seconds before requesting another."
            )

    if not force and user.email_verification_sent_at and not verification_is_expired(user):
        return False

    token = _prepare_verification_token(user, rotate=force)
    verify_url = _public_url(
        reverse(
            "accounts:verify_registration_email",
            kwargs={"token": token},
        )
    )

    body = f"""
        <div style="font-size:14px;line-height:1.7;color:#303a57;">
            <p style="margin:0 0 14px;">
                Your payment was received and <strong>{escape(intent.studio_name)}</strong> has been created in Encore.
            </p>
            <p style="margin:0 0 14px;">
                Verify this email address to unlock your administrator account. The verification link expires in 24 hours.
            </p>
            <div style="padding:14px 16px;background:#f5f7ff;border:1px solid #e0e6ff;border-radius:10px;color:#4b5675;">
                After verification, sign in with the password you created during registration. Your guided Encore tutorial will begin the first time you enter the workspace.
            </div>
        </div>
    """

    html = _email_shell(
        eyebrow="Verify your email",
        heading="Your Encore studio is ready",
        intro=f"Hi {user.first_name or 'there'}, one quick step remains before you sign in.",
        body_html=body,
        button_label="Verify Email & Continue",
        button_url=verify_url,
    )

    text = (
        f"Encore Performance Suite\n\n"
        f"Hi {user.first_name or 'there'},\n\n"
        f"Your payment was received and {intent.studio_name} has been created. "
        f"Verify your email before signing in.\n\n"
        f"Verify email: {verify_url}\n\n"
        f"This link expires in 24 hours."
    )

    send_email(
        to=[user.email],
        subject="Verify your Encore Performance Suite account",
        html_body=html,
        text_body=text,
        tags={
            "message_type": "owner_email_verification",
            "studio_id": intent.studio_id or "pending",
        },
        sensitive=True,
    )

    user.email_verification_sent_at = now
    user.save(
        update_fields=[
            "email_verification_token",
            "email_verification_sent_at",
        ]
    )
    return True


def signup_receipt_context(intent):
    result = {
        "amount_paid": intent.monthly_price,
        "currency": "USD",
        "invoice_number": "",
        "invoice_id": "",
        "hosted_invoice_url": "",
        "invoice_pdf": "",
        "next_billing_at": None,
        "plan_label": intent.get_plan_tier_display(),
        "student_band": intent.student_band,
        "drawing_board_enabled": intent.drawing_board_enabled,
    }

    if not intent.stripe_checkout_session_id:
        return result

    try:
        stripe.api_key = settings.STRIPE_SECRET_KEY
        checkout = stripe.checkout.Session.retrieve(
            intent.stripe_checkout_session_id,
            expand=["invoice", "subscription"],
        )

        invoice = _stripe_value(checkout, "invoice")
        if isinstance(invoice, str) and invoice:
            invoice = stripe.Invoice.retrieve(invoice)

        subscription = _stripe_value(checkout, "subscription")
        if isinstance(subscription, str) and subscription:
            subscription = stripe.Subscription.retrieve(subscription)

        if invoice:
            amount_paid = _stripe_value(invoice, "amount_paid", None)
            if amount_paid is not None:
                result["amount_paid"] = Decimal(str(amount_paid)) / Decimal("100")
            result["currency"] = str(_stripe_value(invoice, "currency", "usd")).upper()
            result["invoice_number"] = _stripe_value(invoice, "number", "") or ""
            result["invoice_id"] = _stripe_value(invoice, "id", "") or ""
            result["hosted_invoice_url"] = _stripe_value(invoice, "hosted_invoice_url", "") or ""
            result["invoice_pdf"] = _stripe_value(invoice, "invoice_pdf", "") or ""

        if subscription:
            result["next_billing_at"] = _stripe_datetime(
                _stripe_value(subscription, "current_period_end")
            )
    except Exception:
        logger.exception(
            "Unable to load Stripe receipt details for signup intent %s",
            intent.pk,
        )

    return result


def send_purchase_confirmation_email(intent):
    if intent.purchase_confirmation_sent_at:
        return False

    user = _owner_user(intent)
    receipt = signup_receipt_context(intent)

    rows = [
        ("Studio", intent.studio_name),
        ("Plan", receipt["plan_label"]),
        ("Student record band", "0–100" if intent.student_band == "0_100" else intent.student_band.replace("_", "–")),
        ("Drawing Board", "Included (+$39/month)" if intent.drawing_board_enabled else "Not selected"),
        ("Amount paid", f"{_format_money(receipt['amount_paid'])} {receipt['currency']}"),
    ]
    if receipt["invoice_number"]:
        rows.append(("Invoice", receipt["invoice_number"]))
    if receipt["next_billing_at"]:
        rows.append(("Next billing date", receipt["next_billing_at"].strftime("%B %d, %Y").replace(" 0", " ")))

    table_rows = "".join(
        f"<tr><td style='padding:10px 12px;color:#66708a;border-bottom:1px solid #edf0f7;'>{escape(label)}</td>"
        f"<td style='padding:10px 12px;color:#121943;font-weight:700;border-bottom:1px solid #edf0f7;text-align:right;'>{escape(str(value))}</td></tr>"
        for label, value in rows
    )

    invoice_link = ""
    if receipt["hosted_invoice_url"]:
        invoice_link = (
            f"<p style='margin:18px 0 0;'><a href='{escape(receipt['hosted_invoice_url'])}' "
            "style='color:#3047f4;font-weight:800;'>View Stripe invoice / receipt →</a></p>"
        )

    body = f"""
        <div style="border:1px solid #e5e9f3;border-radius:12px;overflow:hidden;">
            <table style="width:100%;border-collapse:collapse;font-size:14px;">{table_rows}</table>
        </div>
        {invoice_link}
        <p style="font-size:13px;line-height:1.65;color:#66708a;margin:20px 0 0;">
            Encore subscriptions renew monthly unless cancelled in accordance with your subscription terms. Your billing history and future invoices are also available inside Encore.
        </p>
    """

    html = _email_shell(
        eyebrow="Purchase confirmation",
        heading="Payment received",
        intro=f"Thanks, {user.first_name or 'there'}. Your Encore subscription for {intent.studio_name} is active.",
        body_html=body,
        button_label="View Your Encore Account",
        button_url=_public_url(reverse("accounts:login")),
    )

    text_lines = [
        "Encore Performance Suite - Purchase Confirmation",
        "",
        f"Studio: {intent.studio_name}",
        f"Plan: {receipt['plan_label']}",
        f"Amount paid: {_format_money(receipt['amount_paid'])} {receipt['currency']}",
    ]
    if receipt["invoice_number"]:
        text_lines.append(f"Invoice: {receipt['invoice_number']}")
    if receipt["hosted_invoice_url"]:
        text_lines.append(f"Stripe invoice / receipt: {receipt['hosted_invoice_url']}")

    send_email(
        to=[user.email],
        subject=f"Encore purchase confirmation - {intent.studio_name}",
        html_body=html,
        text_body="\n".join(text_lines),
        tags={
            "message_type": "signup_purchase_confirmation",
            "studio_id": intent.studio_id or "pending",
        },
        
    )

    intent.purchase_confirmation_sent_at = timezone.now()
    intent.save(update_fields=["purchase_confirmation_sent_at", "updated_at"])
    return True


def send_welcome_email(intent):
    if intent.welcome_email_sent_at:
        return False

    user = _owner_user(intent)
    studio = intent.studio

    support_url = _public_url(reverse("support_center:home"))
    settings_url = _public_url(
        reverse("studios:onboarding_home", kwargs={"studio_slug": studio.slug})
    )
    onboarding_url = _public_url(
        reverse(
            "studios:onboarding_meeting_request",
            kwargs={"studio_slug": studio.slug},
        )
    )

    body = f"""
        <div style="display:grid;gap:12px;">
            <div style="padding:16px;border:1px solid #e3e8f7;border-radius:12px;">
                <strong style="display:block;color:#111a4e;margin-bottom:5px;">1. Verify your email</strong>
                <span style="font-size:14px;line-height:1.6;color:#5f6983;">Use the separate verification message we sent before signing in.</span>
            </div>
            <div style="padding:16px;border:1px solid #e3e8f7;border-radius:12px;">
                <strong style="display:block;color:#111a4e;margin-bottom:5px;">2. Take the guided tour</strong>
                <span style="font-size:14px;line-height:1.6;color:#5f6983;">When you first enter Encore, a short tutorial will introduce the workspace, Settings, Data Import & Export, and other key areas.</span>
            </div>
            <div style="padding:16px;border:1px solid #e3e8f7;border-radius:12px;">
                <strong style="display:block;color:#111a4e;margin-bottom:5px;">3. Bring your studio data over</strong>
                <span style="font-size:14px;line-height:1.6;color:#5f6983;">Start from Data Import & Export, use a guided vendor workflow, or request an onboarding meeting with Encore.</span>
            </div>
        </div>
        <div style="margin-top:22px;display:flex;gap:10px;flex-wrap:wrap;">
            <a href="{escape(settings_url)}" style="color:#3047f4;font-weight:800;text-decoration:none;margin-right:16px;">Studio Settings →</a>
            <a href="{escape(onboarding_url)}" style="color:#3047f4;font-weight:800;text-decoration:none;margin-right:16px;">Request Onboarding →</a>
            <a href="{escape(support_url)}" style="color:#3047f4;font-weight:800;text-decoration:none;">Support Center →</a>
        </div>
    """

    html = _email_shell(
        eyebrow="Welcome to Encore",
        heading=f"Welcome, {user.first_name or 'there'}!",
        intro=f"{intent.studio_name} now has its own Encore Performance Suite workspace. Here is what to expect when you get started.",
        body_html=body,
        button_label="Sign In to Encore",
        button_url=_public_url(reverse("accounts:login")),
    )

    text = (
        f"Welcome to Encore Performance Suite\n\n"
        f"{intent.studio_name} is ready.\n\n"
        f"After you verify your email and sign in, Encore will run a guided tutorial. "
        f"You can also request an onboarding meeting or use the Support Center.\n\n"
        f"Settings: {settings_url}\n"
        f"Request onboarding: {onboarding_url}\n"
        f"Support Center: {support_url}\n"
    )

    send_email(
        to=[user.email],
        subject=f"Welcome to Encore Performance Suite - {intent.studio_name}",
        html_body=html,
        text_body=text,
        tags={
            "message_type": "signup_welcome",
            "studio_id": intent.studio_id or "pending",
        },
        
    )

    intent.welcome_email_sent_at = timezone.now()
    intent.save(update_fields=["welcome_email_sent_at", "updated_at"])
    return True


def create_welcome_notifications(intent):
    if not intent.studio_id:
        return

    user = _owner_user(intent)
    studio = intent.studio

    items = [
        {
            "kind": "welcome",
            "title": "Welcome to Encore Performance Suite",
            "message": (
                "Your studio workspace is ready. Start with the guided tutorial and Studio Settings to personalize Encore for your team."
            ),
            "action_url": reverse(
                "studios:onboarding_home",
                kwargs={"studio_slug": studio.slug},
            ),
            "dedupe_key": f"signup-welcome:{intent.pk}",
        },
        {
            "kind": "welcome_onboarding",
            "title": "Want help onboarding your studio?",
            "message": (
                "Encore can help plan your setup, migration, and first steps. Request an onboarding meeting whenever you are ready."
            ),
            "action_url": reverse(
                "studios:onboarding_meeting_request",
                kwargs={"studio_slug": studio.slug},
            ),
            "dedupe_key": f"signup-onboarding:{intent.pk}",
        },
        {
            "kind": "welcome_support",
            "title": "Explore the Encore Support Center",
            "message": (
                "Search step-by-step guides, feature explanations, automatic workflows, setup help, and related questions as you learn Encore."
            ),
            "action_url": reverse("support_center:home"),
            "dedupe_key": f"signup-support:{intent.pk}",
        },
    ]

    for item in items:
        create_workspace_notification(
            studio=studio,
            user=user,
            category=WorkspaceNotification.Category.SYSTEM,
            **item,
        )


def ensure_signup_communications(intent):
    if not intent.studio_id or intent.status != StudioSignupIntent.Status.PAID:
        return

    try:
        create_welcome_notifications(intent)
    except Exception:
        logger.exception(
            "Unable to create welcome notifications for signup intent %s",
            intent.pk,
        )

    for sender in (
        send_verification_email,
        send_purchase_confirmation_email,
        send_welcome_email,
    ):
        try:
            sender(intent)
        except Exception:
            logger.exception(
                "Unable to send signup communication %s for intent %s",
                sender.__name__,
                intent.pk,
            )
