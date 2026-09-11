import stripe
from django.conf import settings
from django.urls import reverse

from .models import StudioSubscription


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


def sync_connected_account(subscription):
    if not subscription.stripe_connected_account_id:
        subscription.payments_connected = False
        subscription.stripe_connect_details_submitted = False
        subscription.stripe_connect_charges_enabled = False
        subscription.stripe_connect_payouts_enabled = False
        subscription.save(
            update_fields=[
                "payments_connected",
                "stripe_connect_details_submitted",
                "stripe_connect_charges_enabled",
                "stripe_connect_payouts_enabled",
                "updated_at",
            ]
        )
        return None

    configure_stripe()

    account = stripe.Account.retrieve(
        subscription.stripe_connected_account_id
    )

    subscription.stripe_connect_details_submitted = bool(
        stripe_value(account, "details_submitted", False)
    )
    subscription.stripe_connect_charges_enabled = bool(
        stripe_value(account, "charges_enabled", False)
    )
    subscription.stripe_connect_payouts_enabled = bool(
        stripe_value(account, "payouts_enabled", False)
    )
    subscription.payments_connected = (
        subscription.stripe_connect_details_submitted
        and subscription.stripe_connect_charges_enabled
        and subscription.stripe_connect_payouts_enabled
    )

    subscription.save(
        update_fields=[
            "payments_connected",
            "stripe_connect_details_submitted",
            "stripe_connect_charges_enabled",
            "stripe_connect_payouts_enabled",
            "updated_at",
        ]
    )

    return account


def get_or_create_connected_account(
    subscription,
    *,
    owner_email="",
):
    configure_stripe()

    if subscription.stripe_connected_account_id:
        return sync_connected_account(subscription)

    studio = subscription.studio

    account = stripe.Account.create(
        type="express",
        country="US",
        email=studio.email or owner_email or None,
        capabilities={
            "card_payments": {
                "requested": True,
            },
            "transfers": {
                "requested": True,
            },
        },
        metadata={
            "encore_studio_id": str(studio.pk),
            "encore_studio_slug": studio.slug,
        },
    )

    subscription.stripe_connected_account_id = account.id
    subscription.save(
        update_fields=[
            "stripe_connected_account_id",
            "updated_at",
        ]
    )

    sync_connected_account(subscription)

    return account


def create_account_link(
    request,
    subscription,
    *,
    owner_email="",
):
    account = get_or_create_connected_account(
        subscription,
        owner_email=owner_email,
    )

    refresh_url = request.build_absolute_uri(
        reverse(
            "billing:stripe_connect_refresh",
            kwargs={
                "studio_slug": subscription.studio.slug,
            },
        )
    )

    return_url = request.build_absolute_uri(
        reverse(
            "billing:stripe_connect_return",
            kwargs={
                "studio_slug": subscription.studio.slug,
            },
        )
    )

    configure_stripe()

    return stripe.AccountLink.create(
        account=account.id,
        refresh_url=refresh_url,
        return_url=return_url,
        type="account_onboarding",
    )


def subscription_for_connected_account(account_id):
    if not account_id:
        return None

    return (
        StudioSubscription.objects
        .filter(
            stripe_connected_account_id=account_id,
        )
        .select_related("studio")
        .first()
    )
