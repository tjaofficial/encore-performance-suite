"""Stripe Connect onboarding for independent dance studios.

New studios use Accounts v2 merchant + full dashboard + Stripe-managed risk.
Existing account IDs remain usable; test/live IDs are stored separately.
"""
import logging

import stripe
from django.conf import settings
from django.urls import reverse

from .models import StudioSubscription
from .stripe_environment import stripe_mode

logger = logging.getLogger(__name__)


def configure_stripe():
    stripe.api_key = settings.STRIPE_SECRET_KEY


def stripe_value(resource, key, default=None):
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


def _account_id(subscription):
    return (subscription.stripe_test_connected_account_id if stripe_mode() == 'test'
            else subscription.stripe_connected_account_id)


def _stripe_client():
    if not hasattr(stripe, 'StripeClient'):
        raise ValueError('Your stripe-python SDK is too old for Accounts v2. Upgrade the stripe package.')
    client = stripe.StripeClient(settings.STRIPE_SECRET_KEY)
    if not hasattr(client, 'v2') or not hasattr(client.v2.core, 'accounts'):
        raise ValueError('Your stripe-python SDK lacks Accounts v2. Upgrade the stripe package.')
    return client


def sync_connected_account(subscription):
    account_id = _account_id(subscription)
    if not account_id:
        if stripe_mode() == 'live':
            subscription.payments_connected = False
            subscription.save(update_fields=['payments_connected', 'updated_at'])
        return None
    configure_stripe()
    # Stripe still supports v1 compatibility retrieval for Accounts v2 IDs.
    account = stripe.Account.retrieve(account_id)
    if stripe_mode() == 'live':
        subscription.stripe_connect_details_submitted = bool(stripe_value(account, 'details_submitted', False))
        subscription.stripe_connect_charges_enabled = bool(stripe_value(account, 'charges_enabled', False))
        subscription.stripe_connect_payouts_enabled = bool(stripe_value(account, 'payouts_enabled', False))
        subscription.payments_connected = (subscription.stripe_connect_details_submitted
            and subscription.stripe_connect_charges_enabled and subscription.stripe_connect_payouts_enabled)
        subscription.save(update_fields=['stripe_connect_details_submitted', 'stripe_connect_charges_enabled',
            'stripe_connect_payouts_enabled', 'payments_connected', 'updated_at'])
    return account


def get_or_create_connected_account(subscription, *, owner_email=''):
    existing = _account_id(subscription)
    if existing:
        return sync_connected_account(subscription)

    studio = subscription.studio
    # These business-owned merchant accounts receive DIRECT charges. Stripe
    # collects fees and bears negative-balance liability. A full Stripe
    # dashboard lets the owner manage their independent studio payments.
    params = {
        'contact_email': studio.email or owner_email or None,
        'display_name': studio.name,
        'dashboard': 'full',
        'identity': {'country': 'us'},
        'configuration': {
            'merchant': {'capabilities': {'card_payments': {'requested': True}}},
        },
        'defaults': {
            'currency': 'usd',
            'responsibilities': {
                'fees_collector': 'stripe',
                'losses_collector': 'stripe',
            },
        },
        'metadata': {
            'encore_studio_id': str(studio.pk),
            'encore_studio_slug': studio.slug,
            'mode': stripe_mode(),
        },
    }
    if not params['contact_email']:
        del params['contact_email']

    client = _stripe_client()
    try:
        account = client.v2.core.accounts.create(params)
    except (TypeError, AttributeError) as exc:
        raise ValueError('The installed stripe-python SDK does not support this Accounts v2 request. Upgrade stripe-python.') from exc

    account_id = stripe_value(account, 'id', '')
    if not account_id or not account_id.startswith('acct_'):
        raise ValueError('Stripe did not return a connected account ID. No account was saved.')
    if stripe_mode() == 'test':
        subscription.stripe_test_connected_account_id = account_id
        subscription.save(update_fields=['stripe_test_connected_account_id', 'updated_at'])
    else:
        subscription.stripe_connected_account_id = account_id
        subscription.save(update_fields=['stripe_connected_account_id', 'updated_at'])
    # Do NOT create a second account on an onboarding failure. The ID is
    # persisted before requesting a single-use onboarding link.
    return account


def create_account_link(request, subscription, *, owner_email=''):
    account = get_or_create_connected_account(subscription, owner_email=owner_email)
    account_id = stripe_value(account, 'id', '')
    if not account_id:
        raise ValueError('Stripe connected account ID is missing.')
    refresh_url = request.build_absolute_uri(reverse('billing:stripe_connect_refresh',
        kwargs={'studio_slug': subscription.studio.slug}))
    return_url = request.build_absolute_uri(reverse('billing:stripe_connect_return',
        kwargs={'studio_slug': subscription.studio.slug}))
    configure_stripe()
    return stripe.AccountLink.create(
        account=account_id, refresh_url=refresh_url,
        return_url=return_url, type='account_onboarding',
    )


def subscription_for_connected_account(account_id):
    if not account_id:
        return None
    field = ('stripe_test_connected_account_id' if stripe_mode() == 'test'
             else 'stripe_connected_account_id')
    return StudioSubscription.objects.filter(**{field: account_id}).select_related('studio').first()
