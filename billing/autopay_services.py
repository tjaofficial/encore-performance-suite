"""Stripe Connect family AutoPay: consent-based, per-studio, per-environment."""
import logging
from datetime import timedelta
from decimal import Decimal
import stripe
from django.db import transaction
from django.utils import timezone
from django.urls import reverse

from .models import Charge, FamilyAccount, FamilyAutoPayAttempt, FamilyAutoPayProfile
from .stripe_environment import connected_account_for_subscription, stripe_mode
from .subscription_services import configure_stripe, stripe_value, stripe_metadata
from .parent_payment_services import (finalize_family_balance_payment, _apply_available_credits,
    family_connected_customer, pending_family_intents)

logger = logging.getLogger(__name__)


class AutoPaySetupPending(ValueError):
    """Stripe has not finished verifying a saved payment method."""


def _stripe_id(value):
    """An expanded Stripe customer/payment method or its string ID."""
    if isinstance(value, str):
        return value
    return str(stripe_value(value, "id", "") or "")


def current_profile(account, subscription):
    mode = stripe_mode()
    connected_id = connected_account_for_subscription(subscription)
    profile, _ = FamilyAutoPayProfile.objects.get_or_create(account=account, mode=mode,
        defaults={"connected_account_id": connected_id})
    if profile.connected_account_id != connected_id:
        # Old saved payment methods can never be used in a different Connect account.
        profile.connected_account_id = connected_id
        profile.stripe_customer_id = ""
        profile.stripe_payment_method_id = ""
        profile.enabled_at = None
        profile.payment_method_type = ""
        profile.card_brand = ""
        profile.card_last4 = ""
        profile.save(update_fields=["connected_account_id", "stripe_customer_id", "stripe_payment_method_id",
            "enabled_at", "payment_method_type", "card_brand", "card_last4", "updated_at"])
    return profile


def create_setup_intent(account, subscription, guardian, method_type):
    if method_type not in {"card", "us_bank_account"}:
        raise ValueError("Choose Bank account (ACH) or Credit/debit card before continuing.")
    profile = family_connected_customer(account, subscription,
        email=(guardian.user.email or guardian.email or ""))
    configure_stripe()
    # Accounts on the newer API reject payment_method_types. The supported
    # allowed_payment_method_types option explicitly limits this SetupIntent
    # to the method the parent selected. A Link wallet token is not ACH.
    setup = stripe.SetupIntent.create(
        customer=profile.stripe_customer_id,
        usage="off_session",
        allowed_payment_method_types=[method_type],
        metadata={"encore_family_account_id": str(account.pk), "encore_studio_id": str(account.studio_id), "encore_autopay_method": method_type},
        stripe_account=profile.connected_account_id,
    )
    return {"client_secret": setup.client_secret, "setup_intent_id": setup.id}


def activate_from_setup(account, subscription, guardian, setup_intent_id):
    if not guardian.is_primary:
        raise ValueError("Only the primary guardian can authorize AutoPay.")
    profile = current_profile(account, subscription)
    configure_stripe()
    setup = stripe.SetupIntent.retrieve(setup_intent_id, stripe_account=profile.connected_account_id)
    metadata = stripe_metadata(setup)
    state = stripe_value(setup, "status", "")
    # Do not grant AutoPay consent while Stripe is verifying a bank account.
    if state in {"processing", "requires_action", "requires_confirmation"}:
        raise AutoPaySetupPending(
            "Stripe is still verifying your payment method. AutoPay is not enabled yet. "
            "Please complete any verification requested by Stripe and choose Check Verification again."
        )
    if state != "succeeded":
        logger.warning("AutoPay setup %s is not complete (status=%s)", setup_intent_id, state)
        raise ValueError(
            "Stripe has not successfully saved this payment method "
            f"(status: {state or 'unknown'}). Please select a method and try again."
        )
    # The server has already checked the primary guardian and matched this
    # SetupIntent to the signed-in family's ID in their Django session.
    # Stripe customer ownership is a second, independent boundary.
    setup_customer_id = _stripe_id(stripe_value(setup, "customer"))
    if not setup_customer_id or setup_customer_id != profile.stripe_customer_id:
        logger.error("AutoPay SetupIntent %s customer mismatch for account %s", setup_intent_id, account.pk)
        raise ValueError("Stripe setup was linked to a different customer record. Please restart setup.")

    # The Django session ties this SetupIntent ID to the authenticated family,
    # and the SetupIntent customer is independently required to equal this
    # family's persisted Stripe customer ID (on this connected account).
    # Stripe metadata is useful for auditing, but can be absent from certain
    # representations. Never require its presence as an extra identity proof;
    # do reject it if it explicitly identifies a different family or studio.
    setup_family_id = str(metadata.get("encore_family_account_id") or "").strip()
    setup_studio_id = str(metadata.get("encore_studio_id") or "").strip()
    if setup_family_id and setup_family_id != str(account.pk):
        logger.error("AutoPay SetupIntent %s family metadata conflicts with account %s",
                     setup_intent_id, account.pk)
        raise ValueError("Stripe setup explicitly references a different family. Please restart setup.")
    if setup_studio_id and setup_studio_id != str(account.studio_id):
        logger.error("AutoPay SetupIntent %s studio metadata conflicts with studio %s",
                     setup_intent_id, account.studio_id)
        raise ValueError("Stripe setup explicitly references a different studio. Please restart setup.")
    if not setup_family_id:
        logger.info("AutoPay SetupIntent %s lacks family metadata; verified by session and connected-account customer match",
                    setup_intent_id)
    method_id = stripe_value(setup, "payment_method")
    if not method_id:
        raise ValueError("No payment method was returned by Stripe.")
    method = stripe.PaymentMethod.retrieve(method_id, stripe_account=profile.connected_account_id)
    method_type = stripe_value(method, "type", "")
    expected_method = str(metadata.get("encore_autopay_method") or "")
    if expected_method and method_type != expected_method:
        raise ValueError("The payment method differs from the selected AutoPay option. Please restart setup.")
    if method_type not in {"card", "us_bank_account"}:
        logger.info("AutoPay SetupIntent %s returned unsupported method type %s", setup_intent_id, method_type)
        raise ValueError(
            f"Stripe saved this as a {method_type or 'unknown'} payment method. "
            "Encore AutoPay currently requires a reusable card or US bank debit. "
            "Choose the bank-account or card option directly in Stripe's secure form."
        )
    if _stripe_id(stripe_value(method, "customer")) != profile.stripe_customer_id:
        raise ValueError("This saved payment method does not belong to your family's Stripe customer.")
    card = stripe_value(method, "card", {}) if method_type == "card" else {}
    bank = stripe_value(method, "us_bank_account", {}) if method_type == "us_bank_account" else {}
    if method_type == "us_bank_account" and not stripe_value(bank, "last4"):
        raise ValueError("The bank account needs to be verified before AutoPay can be enabled.")
    profile.stripe_payment_method_id = method_id
    profile.payment_method_type = method_type
    profile.card_brand = (stripe_value(card, "brand", "") or "") if method_type == "card" else (stripe_value(bank, "bank_name", "") or "Bank account")
    profile.card_last4 = stripe_value(card if method_type == "card" else bank, "last4", "") or ""
    profile.enabled_at = timezone.now()
    profile.consent_user = guardian.user
    was_enabled = profile.account.autopay_enabled
    profile.save(update_fields=["stripe_payment_method_id", "payment_method_type", "card_brand", "card_last4", "enabled_at", "consent_user", "updated_at"])
    account.autopay_enabled = True  # compatibility with existing account status
    account.save(update_fields=["autopay_enabled", "updated_at"])
    if not was_enabled:
        _queue_family_email_on_commit(account.pk, "autopay_enabled",
            f"autopay-enabled:{setup_intent_id}", "AutoPay enabled",
            "AutoPay is now enabled for your family. Future tuition payments follow the scheduled due dates. No payment is collected merely because AutoPay was enabled unless you separately authorized an existing-balance payment.")
    return profile


def disable_autopay(account, subscription):
    was_enabled = account.autopay_enabled
    profile = current_profile(account, subscription)
    profile.enabled_at = None
    profile.save(update_fields=["enabled_at", "updated_at"])
    account.autopay_enabled = False
    account.save(update_fields=["autopay_enabled", "updated_at"])
    if was_enabled:
        _queue_family_email_on_commit(account.pk, "autopay_disabled",
            f"autopay-disabled:{profile.pk}:{profile.updated_at.isoformat()}",
            "AutoPay disabled", "AutoPay has been disabled. Any existing enrollment and tuition balance remains in place. Please pay your upcoming tuition through your family billing account.")


def _queue_family_email_on_commit(account_id, event, key, subject, message):
    from .email_notifications import queue_billing_notice
    def enqueue():
        account = FamilyAccount.objects.select_related("studio", "family").get(pk=account_id)
        queue_billing_notice(account, event, key, f"{account.studio.name} — {subject}", message)
    transaction.on_commit(enqueue)


def _notify(profile, kind, title, message, key):
    from communications.models import WorkspaceNotification
    from communications.notification_services import create_workspace_notification
    from families.models import Guardian
    for guardian in Guardian.objects.filter(family=profile.account.family, is_active=True, user__isnull=False).select_related("user"):
        create_workspace_notification(studio=profile.account.studio, user=guardian.user,
            category=WorkspaceNotification.Category.SYSTEM, kind=kind, title=title, message=message,
            action_url=reverse("billing:family_payments", kwargs={"studio_slug": profile.account.studio.slug}) + "#autopay",
            dedupe_key=f"{key}:{guardian.user_id}")


def update_autopay_attempt_from_intent(intent, connected_account_id):
    """Idempotent settlement/failure handling for Connect payment webhooks.

    An ACH debit can be processing for days. Never allocate its balance until
    payment_intent.succeeded has been received or independently verified.
    """
    intent_id = stripe_value(intent, "id", "")
    metadata = stripe_metadata(intent)
    charge_id = str(metadata.get("autopay_charge_id", ""))
    if not charge_id.isdigit() or metadata.get("encore_kind") != "family_balance_payment":
        return None
    with transaction.atomic():
        attempt = (FamilyAutoPayAttempt.objects.select_for_update()
            .select_related("profile", "charge__account")
            .filter(charge_id=int(charge_id), stripe_payment_intent_id=intent_id,
                    profile__connected_account_id=connected_account_id).first())
        if not attempt:
            return None
        state = stripe_value(intent, "status", "")
        if state == "succeeded":
            payment = finalize_family_balance_payment(intent, connected_account_id=connected_account_id)
            if payment is None:
                raise ValueError("Stripe succeeded but Encore could not finalize this tuition payment.")
            if attempt.status != "succeeded":
                attempt.status = "succeeded"
                attempt.save(update_fields=["status", "updated_at"])
                _notify(attempt.profile, "autopay_succeeded", "Automatic Tuition Payment Received",
                    "Your automatic tuition payment was successful.", f"autopay-success-{attempt.charge_id}")
        elif state in {"requires_payment_method", "canceled"}:
            if attempt.status not in {"failed", "succeeded"}:
                attempt.status = "failed"
                attempt.save(update_fields=["status", "updated_at"])
                _notify(attempt.profile, "autopay_failed", "AutoPay Payment Failed",
                    "The automatic tuition payment was unsuccessful. Please review your payment method in Billing.",
                    f"autopay-failure-{attempt.charge_id}")
                _queue_family_email_on_commit(attempt.charge.account_id, "payment_failed",
                    f"autopay-failure:{attempt.pk}", "Automatic tuition payment failed",
                    "An automatic tuition payment was unsuccessful. Your tuition balance has not been cleared. Please review your saved payment method and contact your studio if you need assistance.")
        elif state in {"processing", "requires_action", "requires_confirmation", "requires_capture"}:
            if attempt.status != state and attempt.status != "succeeded":
                attempt.status = state
                attempt.save(update_fields=["status", "updated_at"])
                if state == "processing":
                    _queue_family_email_on_commit(attempt.charge.account_id, "ach_pending",
                        f"autopay-processing:{attempt.pk}", "Bank payment processing",
                        "Your automatic bank payment is processing. This is not a receipt. Your balance will only be marked paid when Stripe confirms settlement.")
        return attempt


def collect_due_autopay(as_of=None, dry_run=True):
    """Run daily after charge generation; process only post-consent recurring tuition.

    One attempt per charge; no automatic retries after uncertain failure.
    """
    as_of = as_of or timezone.localdate()
    results = {"eligible": 0, "succeeded": 0, "processing": 0, "failed": 0, "skipped": 0}
    charges = (Charge.objects.filter(charge_type=Charge.ChargeType.TUITION,
        recurring_schedule__isnull=False, due_date__lte=as_of,
        status__in=[Charge.Status.OPEN, Charge.Status.PARTIALLY_PAID])
        .select_related("account", "account__studio", "recurring_schedule"))
    for charge in charges:
        subscription = getattr(charge.account.studio, "subscription", None)
        if not subscription:
            continue
        try:
            profile = current_profile(charge.account, subscription)
        except ValueError:
            continue
        if not profile.is_enabled or charge.due_date < timezone.localtime(profile.enabled_at).date():
            continue
        if FamilyAutoPayAttempt.objects.filter(charge_id=charge.pk).exists():
            results["skipped"] += 1
            continue
        if not dry_run:
            _apply_available_credits(charge.account)
            charge.refresh_from_db()
        balance = charge.balance_remaining
        if balance <= Decimal("0"):
            continue
        results["eligible"] += 1
        if dry_run:
            continue
        with transaction.atomic():
            locked = Charge.objects.select_for_update().get(pk=charge.pk)
            if FamilyAutoPayAttempt.objects.filter(charge=locked).exists():
                results["skipped"] += 1
                continue
            balance = locked.balance_remaining
            if balance <= Decimal("0"):
                results["skipped"] += 1
                continue
            attempt = FamilyAutoPayAttempt.objects.create(charge=locked, profile=profile)
        try:
            configure_stripe()
            intent = stripe.PaymentIntent.create(
                amount=int(balance * 100), currency="usd",
                customer=profile.stripe_customer_id,
                payment_method=profile.stripe_payment_method_id,
                off_session=True, confirm=True,
                metadata={"encore_kind": "family_balance_payment",
                    "studio_id": str(charge.account.studio_id),
                    "family_account_id": str(charge.account_id),
                    "family_id": str(charge.account.family_id),
                    "autopay_charge_id": str(charge.pk)},
                stripe_account=profile.connected_account_id,
                idempotency_key=f"encore-autopay-{profile.mode}-{charge.pk}")
            attempt.stripe_payment_intent_id = intent.id
            # Store the intent ID before reconciliation; never treat a pending
            # ACH debit as paid, and allow the first successful result to
            # generate one notification.
            attempt.status = "submitted"
            attempt.save(update_fields=["stripe_payment_intent_id", "status", "updated_at"])
            update_autopay_attempt_from_intent(intent, profile.connected_account_id)
            if attempt.status == "succeeded" or stripe_value(intent, "status") == "succeeded":
                results["succeeded"] += 1
            elif stripe_value(intent, "status") in {"processing", "requires_action", "requires_confirmation"}:
                results["processing"] += 1
            else:
                results["failed"] += 1
        except stripe.error.StripeError as exc:
            attempt.status = "failed"
            attempt.error_message = str(exc)[:1000]
            attempt.save(update_fields=["status", "error_message", "updated_at"])
            results["failed"] += 1
            logger.warning("AutoPay failed for charge %s: %s", charge.pk, exc)
            _notify(profile, "autopay_failed", "AutoPay Payment Failed",
                "Your tuition payment failed. Review Billing to update your payment method.",
                f"autopay-failure-{charge.pk}")
    return results


def reconcile_pending_autopay(dry_run=True):
    """Recover delayed/missed Stripe webhooks safely without creating new charges."""
    results = {"pending": 0, "checked": 0, "errors": 0}
    for attempt in FamilyAutoPayAttempt.objects.exclude(
        status__in=["succeeded", "failed"]).exclude(stripe_payment_intent_id="").select_related("profile"):
        results["pending"] += 1
        if dry_run:
            continue
        try:
            configure_stripe()
            intent = stripe.PaymentIntent.retrieve(attempt.stripe_payment_intent_id,
                stripe_account=attempt.profile.connected_account_id)
            update_autopay_attempt_from_intent(intent, attempt.profile.connected_account_id)
            results["checked"] += 1
        except (stripe.error.StripeError, ValueError):
            logger.exception("Unable to reconcile Stripe AutoPay attempt %s", attempt.pk)
            results["errors"] += 1
    return results

def send_autopay_reminders(as_of=None, dry_run=True):
    as_of = as_of or timezone.localdate()
    results = {"eligible": 0, "sent": 0}
    for account in FamilyAccount.objects.filter(is_active=True).select_related("studio", "family"):
        subscription = getattr(account.studio, "subscription", None)
        if not subscription:
            continue
        try:
            profile = current_profile(account, subscription)
        except ValueError:
            continue
        if profile.is_enabled:
            continue
        next_due = account.recurring_schedules.filter(is_active=True, next_charge_date__gte=as_of,
            next_charge_date__lte=as_of + timedelta(days=5)).order_by("next_charge_date").first()
        if not next_due:
            continue
        results["eligible"] += 1
        if not dry_run:
            _notify(profile, "autopay_reminder", "Make Tuition Payments Easier",
                "Your tuition payment is approaching. Enable AutoPay in Billing to pay automatically each month.",
                f"autopay-reminder-{account.pk}-{next_due.next_charge_date:%Y-%m}")
            results["sent"] += 1
    return results


def collect_activation_balance_once(account, subscription, profile, *, recovery=False):
    """Initiate a single, consented payment of the *current* outstanding balance.

    Stripe's idempotency key is stable for this particular AutoPay activation.
    The normal Connect webhook settles the payment (including delayed ACH).
    This function intentionally never retries a failed/uncertain collection.
    """
    if not profile.is_enabled or not profile.enabled_at:
        raise ValueError("AutoPay authorization is required before collecting a balance.")
    if profile.connected_account_id != connected_account_for_subscription(subscription):
        raise ValueError("Saved payment method is not associated with this studio's Stripe account.")
    configure_stripe()
    method = stripe.PaymentMethod.retrieve(profile.stripe_payment_method_id,
        stripe_account=profile.connected_account_id)
    if (_stripe_id(stripe_value(method, "customer")) != profile.stripe_customer_id
            or stripe_value(method, "type") != profile.payment_method_type):
        raise ValueError("Saved payment method no longer belongs to the family Stripe customer.")
    pending = pending_family_intents(account, profile.connected_account_id, profile.stripe_customer_id)
    if pending:
        return {"status": "already_pending", "amount": "0.00", "intent_id": stripe_value(pending[0], "id")}

    # Do not create a second payment while another online balance payment is
    # processing. The family is explicitly shown the amount at setup time.
    from .parent_payment_services import _amount_to_cents
    from .models import Payment
    amount = max(account.balance, Decimal("0.00"))
    if amount <= 0:
        return {"status": "no_balance", "amount": "0.00"}
    # The amount may have changed after authorization due to a manual payment.
    # Never exceed the amount the parent expressly approved.
    authorized = getattr(profile, "_activation_balance_authorized", None)
    if authorized is None:
        raise ValueError("The outstanding balance must be explicitly authorized.")
    amount = min(amount, authorized)
    if amount <= 0:
        return {"status": "no_balance", "amount": "0.00"}
    # A manual recovery is a new payment operation, not a replay of the original
    # activation. Never reuse the original activation key after request parameters
    # have changed: Stripe rejects that with IdempotencyError.
    # Keep the recovery key deterministic so repeated executions of the command
    # cannot create multiple debits for the same activation and approved amount.
    if recovery:
        key = (
            f"encore-family-recovery-v1-{profile.mode}-{account.pk}-"
            f"{profile.pk}-{int(profile.enabled_at.timestamp())}-{_amount_to_cents(amount)}"
        )
    else:
        key = f"encore-family-activation-{profile.mode}-{profile.pk}-{int(profile.enabled_at.timestamp())}"
    params = dict(
        amount=_amount_to_cents(amount), currency="usd",
        customer=profile.stripe_customer_id,
        payment_method=profile.stripe_payment_method_id,
        off_session=True, confirm=True,
        allowed_payment_method_types=[profile.payment_method_type],
        description=f"{account.studio.name} family outstanding balance on AutoPay activation",
        metadata={"encore_kind":"family_balance_payment", "studio_id":str(account.studio_id),
                  "family_account_id":str(account.pk), "family_id":str(account.family_id),
                  "encore_autopay_activation":"true"},
    )
    intent = stripe.PaymentIntent.create(**params, stripe_account=profile.connected_account_id, idempotency_key=key)
    status = stripe_value(intent, "status", "unknown")
    if status == "succeeded":
        finalize_family_balance_payment(intent, connected_account_id=profile.connected_account_id)
    return {"status":status, "amount":f"{amount:.2f}"}
