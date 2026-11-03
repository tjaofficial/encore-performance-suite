"""Connected account readiness and embedded Stripe verification."""
import stripe
from django.conf import settings
from .stripe_environment import stripe_mode
from .connect_services import _stripe_client, stripe_value


def studio_account_id(subscription):
    field = 'stripe_test_connected_account_id' if stripe_mode() == 'test' else 'stripe_connected_account_id'
    return (getattr(subscription, field, '') or '').strip()


def _get(obj, *path, default=None):
    for part in path:
        obj = stripe_value(obj, part, None)
        if obj is None:
            return default
    return obj


def _requirement_items(requirements):
    """Read reported requirements without asserting that an account is verified."""
    seen = set()
    items = []
    for source in (requirements, _get(requirements, 'entries', default={})):
        for key in ('past_due', 'currently_due', 'eventually_due', 'pending_verification'):
            raw = stripe_value(source, key, []) or []
            if not isinstance(raw, (list, tuple)):
                continue
            for entry in raw:
                name = str(stripe_value(entry, 'requirement', None) or stripe_value(entry, 'field', None) or entry)
                unique = (name, key)
                if unique in seen:
                    continue
                seen.add(unique)
                items.append({'name': name, 'urgency': key.replace('_', ' ')})
    return items


def account_readiness(subscription):
    result = {
        'mode': stripe_mode(), 'account_id': studio_account_id(subscription),
        'ready': False, 'account_setup': False, 'charges_enabled': False,
        'payouts_enabled': False, 'message': '', 'requirements': [],
        'card_status': 'pending', 'payout_status': 'not verified',
        'state': 'not_started', 'state_label': 'Not started',
        'action_required': False, 'can_wait': False,
    }
    if not result['account_id']:
        result['message'] = 'Your studio has not started payment account setup.'
        return result
    client = _stripe_client()
    account = client.v2.core.accounts.retrieve(result['account_id'],
        params={'include': ['configuration.merchant', 'requirements', 'defaults']})
    card_status = str(_get(account, 'configuration', 'merchant', 'capabilities',
                           'card_payments', 'status', default='pending') or 'pending').lower()
    result['card_status'] = card_status
    result['charges_enabled'] = card_status == 'active'
    result['account_setup'] = True
    result['requirements'] = _requirement_items(_get(account, 'requirements', default={}) or {})
    # An 'eventually due' item alone need not block today's payments.
    result['action_required'] = any(x['urgency'] in ('past due', 'currently due')
                                    for x in result['requirements'])
    if result['charges_enabled']:
        result.update(ready=True, state='active', state_label='Payments active',
                      message='Your studio can now accept online payments through Stripe.')
    elif result['action_required'] or card_status in ('restricted', 'inactive', 'disabled'):
        result.update(state='action_required', state_label='Action required',
                      message='Stripe needs additional information before card payments can be enabled.')
    else:
        result.update(state='review', state_label='Verification pending', can_wait=True,
                      message='Your information was submitted. Stripe has not enabled card payments yet. No further action is currently shown in Encore; check back for updates.')
    # Never infer bank payout readiness from card payment capability.
    return result


def create_activation_session(subscription):
    account_id = studio_account_id(subscription)
    if not account_id:
        raise ValueError('This studio does not have a connected account yet.')
    stripe.api_key = settings.STRIPE_SECRET_KEY
    session = stripe.AccountSession.create(
        account=account_id,
        components={
            'account_onboarding': {'enabled': True},
            'account_management': {'enabled': True},
            'notification_banner': {'enabled': True},
        },
    )
    secret = stripe_value(session, 'client_secret', '')
    if not secret:
        raise ValueError('Stripe could not create an embedded onboarding session.')
    return secret
