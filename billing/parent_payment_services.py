from decimal import Decimal, ROUND_HALF_UP

import stripe
from django.db import transaction
from django.conf import settings
from django.utils import timezone

from .models import FamilyAccount, Payment, StudioSubscription, FamilyAutoPayProfile
from .services import (
    allocate_credit_to_oldest_open_charges,
    allocate_payment_to_oldest_open_charges,
)
from .subscription_services import configure_stripe, stripe_metadata, stripe_value
from .stripe_environment import connected_account_for_subscription, verify_connected_account, stripe_mode


FAMILY_BALANCE_PAYMENT_KIND = "family_balance_payment"


def _amount_to_cents(amount):
    normalized = Decimal(amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return int(normalized * 100)


def _apply_available_credits(account):
    credits = (
        account.credits
        .filter(is_void=False)
        .order_by("created_at", "pk")
    )

    for credit in credits:
        if credit.remaining_amount > Decimal("0.00"):
            allocate_credit_to_oldest_open_charges(credit)


def family_connected_customer(account, subscription, *, email=""):
    """One customer for both manual payments and AutoPay, per family/mode/Connect account.

    Stripe calls occur on the same connected account. Keep the row locked while
    creating a customer so concurrent browser requests do not create duplicates.
    """
    connected_id = connected_account_for_subscription(subscription)
    mode = stripe_mode()
    configure_stripe()
    with transaction.atomic():
        profile, _ = FamilyAutoPayProfile.objects.get_or_create(
            account=account, mode=mode, defaults={"connected_account_id": connected_id})
        profile = FamilyAutoPayProfile.objects.select_for_update().get(pk=profile.pk)
        if profile.connected_account_id != connected_id:
            # Credentials changed: never reuse tokens from another account.
            profile.connected_account_id = connected_id
            profile.stripe_customer_id = ""
            profile.stripe_payment_method_id = ""
            profile.payment_method_type = ""
            profile.card_brand = ""
            profile.card_last4 = ""
            profile.enabled_at = None
            profile.save(update_fields=["connected_account_id", "stripe_customer_id",
                "stripe_payment_method_id", "payment_method_type", "card_brand",
                "card_last4", "enabled_at", "updated_at"])
        if not profile.stripe_customer_id:
            customer = stripe.Customer.create(
                email=email or None,
                metadata={"encore_family_account_id": str(account.pk),
                          "encore_studio_id": str(account.studio_id)},
                stripe_account=connected_id,
                idempotency_key=f"encore-customer-{mode}-{connected_id}-{account.pk}",
            )
            profile.stripe_customer_id = stripe_value(customer, "id")
            profile.save(update_fields=["stripe_customer_id", "updated_at"])
        return profile


def pending_family_intents(account, connected_id, customer_id):
    """Prevent repeat collection, including activation debits with stripped metadata.

    Return unsettled intents and succeeded-but-unrecorded family payments.
    Only trust payment-method ownership for exact activation descriptions.
    """
    configure_stripe()
    profile = FamilyAutoPayProfile.objects.filter(
        account=account, connected_account_id=connected_id,
        stripe_customer_id=customer_id,
    ).first()
    intents = stripe.PaymentIntent.list(customer=customer_id, limit=100,
                                        stripe_account=connected_id)
    matches = []
    for intent in stripe_value(intents, "data", []) or []:
        meta = stripe_metadata(intent)
        state = stripe_value(intent, "status", "")
        tagged = (meta.get("encore_kind") == FAMILY_BALANCE_PAYMENT_KIND
                  and str(meta.get("family_account_id")) == str(account.pk))
        activation = (profile is not None and bool(profile.enabled_at)
                      and stripe_value(intent, "payment_method") == profile.stripe_payment_method_id
                      and stripe_value(intent, "description", "") ==
                      f"{account.studio.name} family outstanding balance on AutoPay activation"
                      and (stripe_value(intent, "created", 0) or 0) >= int(profile.enabled_at.timestamp()))
        if not (tagged or activation):
            continue
        if state in {"processing", "requires_action", "requires_confirmation", "requires_capture"}:
            matches.append(intent)
        elif state == "succeeded" and not Payment.objects.filter(
                account=account, external_reference=stripe_value(intent, "id", "")).exists():
            matches.append(intent)
    return matches


def create_family_balance_payment_intent(*, account, subscription, receipt_email=""):
    connected_account_id = connected_account_for_subscription(subscription)
    verify_connected_account(connected_account_id)

    _apply_available_credits(account)
    account.refresh_from_db()

    amount_due = max(account.balance, Decimal("0.00"))

    if amount_due <= Decimal("0.00"):
        raise ValueError("This family account does not have a balance due.")

    profile = family_connected_customer(account, subscription, email=receipt_email)
    if pending_family_intents(account, connected_account_id, profile.stripe_customer_id):
        raise ValueError("A family payment is already processing. Wait for it to settle before starting another payment.")

    params = {
        "customer": profile.stripe_customer_id,
        "amount": _amount_to_cents(amount_due),
        "currency": "usd",
        "automatic_payment_methods": {"enabled": True},
        "description": f"{account.studio.name} family account payment",
        "metadata": {
            "encore_kind": FAMILY_BALANCE_PAYMENT_KIND,
            "studio_id": str(account.studio_id),
            "family_account_id": str(account.pk),
            "family_id": str(account.family_id),
        },
    }

    if receipt_email:
        params["receipt_email"] = receipt_email

    payment_intent = stripe.PaymentIntent.create(
        **params,
        stripe_account=connected_account_id,
    )

    return {
        "payment_intent": payment_intent,
        "amount_due": amount_due,
        "client_secret": stripe_value(payment_intent, "client_secret", ""),
        "connected_account_id": connected_account_id,
    }


def _payment_method_for_intent(payment_intent, connected_account_id):
    method_type = ""
    payment_method = stripe_value(payment_intent, "payment_method")

    if isinstance(payment_method, dict):
        method_type = stripe_value(payment_method, "type", "")
    elif payment_method:
        try:
            configure_stripe()
            method_obj = stripe.PaymentMethod.retrieve(
                payment_method,
                stripe_account=connected_account_id,
            )
            method_type = stripe_value(method_obj, "type", "")
        except stripe.error.StripeError:
            method_type = ""

    if method_type == "us_bank_account":
        return Payment.Method.ACH

    return Payment.Method.CARD


def finalize_family_balance_payment(payment_intent, *, connected_account_id=""):
    metadata = stripe_metadata(payment_intent)

    if metadata.get("encore_kind") != FAMILY_BALANCE_PAYMENT_KIND:
        return None

    if stripe_value(payment_intent, "status", "") != "succeeded":
        return None

    account_id = str(metadata.get("family_account_id", "")).strip()
    if not account_id.isdigit():
        return None

    # The webhook already provides the Connect account that received this event.
    # A test account is not the same identifier stored for live Connect onboarding.
    studio_id = str(metadata.get("studio_id", "")).strip()
    if not studio_id.isdigit():
        return None
    subscription = StudioSubscription.objects.select_related("studio").filter(studio_id=int(studio_id)).first()
    if subscription is None:
        return None
    try:
        expected_account = connected_account_for_subscription(subscription)
    except ValueError:
        return None
    if expected_account != connected_account_id:
        return None

    payment_intent_id = stripe_value(payment_intent, "id", "")
    amount_received = stripe_value(payment_intent, "amount_received", 0) or 0

    if not payment_intent_id or amount_received <= 0:
        return None

    amount = (Decimal(str(amount_received)) / Decimal("100")).quantize(
        Decimal("0.01")
    )

    with transaction.atomic():
        account = (
            FamilyAccount.objects
            .select_for_update()
            .select_related("studio", "family")
            .filter(
                pk=int(account_id),
                studio=subscription.studio,
            )
            .first()
        )

        if account is None:
            return None

        # Enforce the configured family customer whenever Stripe provides one.
        intent_customer = stripe_value(payment_intent, "customer")
        if intent_customer:
            profile = FamilyAutoPayProfile.objects.filter(
                account=account, mode=stripe_mode(), connected_account_id=connected_account_id).first()
            if not profile or profile.stripe_customer_id != str(intent_customer):
                raise ValueError("Stripe PaymentIntent customer does not match the family account.")

        existing = account.payments.filter(
            external_reference=payment_intent_id,
        ).first()

        if existing is not None:
            return existing

        payment = Payment.objects.create(
            account=account,
            amount=amount,
            method=_payment_method_for_intent(
                payment_intent,
                connected_account_id,
            ),
            status=Payment.Status.SUCCEEDED,
            paid_at=timezone.now(),
            external_reference=payment_intent_id,
            notes="Online family balance payment processed through Stripe Connect.",
        )

        allocate_payment_to_oldest_open_charges(payment)
        return payment
