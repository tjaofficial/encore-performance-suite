"""Select the correct Stripe Connect account for the configured key mode.

Never use a production studio Connect ID as a fallback for a test payment.
"""
import logging
import stripe
from django.conf import settings

logger = logging.getLogger(__name__)


def stripe_mode():
    secret = (getattr(settings, "STRIPE_SECRET_KEY", "") or "").strip()
    publishable = (getattr(settings, "STRIPE_PUBLISHABLE_KEY", "") or "").strip()
    if secret.startswith("sk_test_") and publishable.startswith("pk_test_"):
        return "test"
    if secret.startswith("sk_live_") and publishable.startswith("pk_live_"):
        return "live"
    raise ValueError("Stripe secret and publishable keys must both use the same test or live mode.")


def connected_account_for_subscription(subscription):
    mode = stripe_mode()
    if mode == "live":
        account = (subscription.stripe_connected_account_id or "").strip()
        if not account or not subscription.payments_connected:
            raise ValueError("This studio has not completed live Stripe Connect onboarding.")
        return account

    account = (subscription.stripe_test_connected_account_id or "").strip()
    if not account.startswith("acct_"):
        raise ValueError("This studio needs test Stripe Connect onboarding before it can accept sandbox payments.")
    return account


def verify_connected_account(account_id):
    """Require Stripe-confirmed card payment capability in the current mode."""
    from .connect_services import _stripe_client, stripe_value
    from .subscription_services import configure_stripe
    configure_stripe()
    try:
        client = _stripe_client()
        account = client.v2.core.accounts.retrieve(
            account_id, params={'include': ['configuration.merchant']}
        )
        merchant = stripe_value(stripe_value(account, 'configuration', {}), 'merchant', {})
        caps = stripe_value(merchant, 'capabilities', {})
        card = stripe_value(caps, 'card_payments', {})
        active = str(stripe_value(card, 'status', '')).lower() == 'active'
    except stripe.error.InvalidRequestError as exc:
        # Older existing connected accounts can still use Accounts v1.
        if 'v1_account_instead_of_v2_account' not in str(exc):
            raise
        account = stripe.Account.retrieve(account_id)
        active = bool(stripe_value(account, 'charges_enabled', False))
    if not active:
        raise ValueError('This studio needs to finish Stripe payment verification before accepting payments.')
    return account
