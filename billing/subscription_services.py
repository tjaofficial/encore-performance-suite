
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal
from uuid import uuid4

import stripe
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from studios.models import (
    Studio,
    StudioMembership,
    StudioSettings,
)

from .models import (
    StudioSignupIntent,
    StudioSubscription,
    SubscriptionNotice,
)


PRICE_CATALOG = {
    "0_100": {
        "label": "0–100",
        "min": 0,
        "max": 100,
        "essentials": Decimal("79.00"),
        "pro": Decimal("99.00"),
    },
    "101_250": {
        "label": "101–250",
        "min": 101,
        "max": 250,
        "essentials": Decimal("109.00"),
        "pro": Decimal("139.00"),
    },
    "251_500": {
        "label": "251–500",
        "min": 251,
        "max": 500,
        "essentials": Decimal("139.00"),
        "pro": Decimal("169.00"),
    },
    "501_1000": {
        "label": "501–1,000",
        "min": 501,
        "max": 1000,
        "essentials": Decimal("159.00"),
        "pro": Decimal("199.00"),
    },
    "1001_2000": {
        "label": "1,001–2,000",
        "min": 1001,
        "max": 2000,
        "essentials": Decimal("199.00"),
        "pro": Decimal("249.00"),
    },
    "2001_3000": {
        "label": "2,001–3,000",
        "min": 2001,
        "max": 3000,
        "essentials": Decimal("239.00"),
        "pro": Decimal("299.00"),
    },
    "3001_5000": {
        "label": "3,001–5,000",
        "min": 3001,
        "max": 5000,
        "essentials": Decimal("299.00"),
        "pro": Decimal("369.00"),
    },
}

DRAWING_BOARD_PRICE = Decimal("39.00")
TERMS_VERSION = "2026-10-02"


def configure_stripe():
    stripe.api_key = settings.STRIPE_SECRET_KEY


def stripe_value(resource, key, default=None):
    """
    Read a value from either a StripeObject or a normal dict.

    Newer stripe-python versions intentionally do not expose dict.get()
    on API resource objects, so Encore uses attribute/item access instead.
    """
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


def stripe_metadata(resource):
    metadata = stripe_value(
        resource,
        "metadata",
        {},
    )

    if metadata is None:
        return {}

    if isinstance(metadata, dict):
        return metadata

    try:
        return dict(metadata)
    except (TypeError, ValueError):
        return {}


def student_band_for_count(count):
    for key, row in PRICE_CATALOG.items():
        if row["min"] <= count <= row["max"]:
            return key

    return "custom"


def subscription_price(
    plan_tier,
    student_band,
    *,
    drawing_board=False,
):
    if student_band == "custom":
        return None

    base = PRICE_CATALOG[
        student_band
    ][plan_tier]

    if drawing_board:
        base += DRAWING_BOARD_PRICE

    return base

def price_catalog_rows():
    rows = []

    for key, row in PRICE_CATALOG.items():
        rows.append(
            {
                "key": key,
                "label": row["label"],
                "essentials": row["essentials"],
                "pro": row["pro"],
            }
        )

    return rows

def _find_or_create_product(
    *,
    name,
    metadata_key,
):
    configure_stripe()

    products = stripe.Product.list(
        active=True,
        limit=100,
    )

    for product in products.auto_paging_iter():
        if (
            stripe_metadata(product).get(
                "encore_product"
            )
            == metadata_key
        ):
            return product

    return stripe.Product.create(
        name=name,
        metadata={
            "encore_product": metadata_key,
        },
    )


def _price_lookup_key(
    *,
    plan_tier,
    student_band,
):
    return (
        f"encore_{plan_tier}_"
        f"{student_band}_monthly"
    )


def ensure_software_price(
    *,
    plan_tier,
    student_band,
):
    configure_stripe()

    amount = subscription_price(
        plan_tier,
        student_band,
    )

    if amount is None:
        raise ValueError(
            "Custom pricing requires manual setup."
        )

    lookup_key = _price_lookup_key(
        plan_tier=plan_tier,
        student_band=student_band,
    )

    expected_unit_amount = int(
        amount * 100
    )

    prices = stripe.Price.list(
        lookup_keys=[
            lookup_key,
        ],
        active=True,
        limit=1,
    )

    if prices.data:
        existing = prices.data[0]
        recurring = stripe_value(
            existing,
            "recurring",
            {},
        ) or {}

        existing_interval = stripe_value(
            recurring,
            "interval",
            "",
        )

        if (
            stripe_value(
                existing,
                "unit_amount",
                0,
            )
            == expected_unit_amount
            and stripe_value(
                existing,
                "currency",
                "",
            )
            == "usd"
            and existing_interval == "month"
        ):
            return existing

        product_id = stripe_value(
            existing,
            "product",
            "",
        )

        if not isinstance(
            product_id,
            str,
        ):
            product_id = stripe_value(
                product_id,
                "id",
                "",
            )

        if not product_id:
            product = _find_or_create_product(
                name="Encore Performance Suite",
                metadata_key="software",
            )
            product_id = product.id

        return stripe.Price.create(
            product=product_id,
            currency="usd",
            unit_amount=expected_unit_amount,
            recurring={
                "interval": "month",
            },
            lookup_key=lookup_key,
            transfer_lookup_key=True,
            metadata={
                "encore_kind": "software",
                "plan_tier": plan_tier,
                "student_band": student_band,
            },
        )

    product = _find_or_create_product(
        name="Encore Performance Suite",
        metadata_key="software",
    )

    return stripe.Price.create(
        product=product.id,
        currency="usd",
        unit_amount=expected_unit_amount,
        recurring={
            "interval": "month",
        },
        lookup_key=lookup_key,
        metadata={
            "encore_kind": "software",
            "plan_tier": plan_tier,
            "student_band": student_band,
        },
    )

def ensure_drawing_board_price():
    configure_stripe()

    lookup_key = (
        "encore_drawing_board_monthly"
    )

    prices = stripe.Price.list(
        lookup_keys=[
            lookup_key,
        ],
        active=True,
        limit=1,
    )

    if prices.data:
        return prices.data[0]

    product = _find_or_create_product(
        name="Encore Drawing Board",
        metadata_key="drawing_board",
    )

    return stripe.Price.create(
        product=product.id,
        currency="usd",
        unit_amount=int(
            DRAWING_BOARD_PRICE
            * 100
        ),
        recurring={
            "interval": "month",
        },
        lookup_key=lookup_key,
        metadata={
            "encore_kind": "drawing_board",
        },
    )


def _subscription_item_kind(item):
    """
    Identify an Encore subscription item without guessing.
    Unknown items intentionally return an empty string.
    """
    price = stripe_value(
        item,
        "price",
    )

    price_metadata = stripe_metadata(
        price
    )

    kind = price_metadata.get(
        "encore_kind",
        "",
    )

    if kind in {
        "software",
        "drawing_board",
    }:
        return kind

    lookup_key = stripe_value(
        price,
        "lookup_key",
        "",
    ) or ""

    if lookup_key == "encore_drawing_board_monthly":
        return "drawing_board"

    if (
        lookup_key.startswith("encore_")
        and lookup_key.endswith("_monthly")
    ):
        return "software"

    product = stripe_value(
        price,
        "product",
    )

    if product and not isinstance(
        product,
        str,
    ):
        product_kind = stripe_metadata(
            product
        ).get(
            "encore_product",
            "",
        )

        if product_kind in {
            "software",
            "drawing_board",
        }:
            return product_kind

    return ""


def _retrieve_subscription_items(subscription):
    configure_stripe()

    stripe_subscription = (
        stripe.Subscription.retrieve(
            subscription.stripe_subscription_id,
            expand=[
                "items.data.price.product",
            ],
        )
    )

    software_items = []
    drawing_board_items = []
    unknown_items = []

    items = stripe_value(
        stripe_value(
            stripe_subscription,
            "items",
            {},
        ),
        "data",
        [],
    ) or []

    for item in items:
        kind = _subscription_item_kind(
            item
        )

        if kind == "software":
            software_items.append(item)
        elif kind == "drawing_board":
            drawing_board_items.append(item)
        else:
            unknown_items.append(item)

    return {
        "subscription": stripe_subscription,
        "software": software_items,
        "drawing_board": drawing_board_items,
        "unknown": unknown_items,
    }


def reconcile_subscription_item_ids(
    subscription,
    *,
    fail_on_duplicates=True,
):
    if not subscription.stripe_subscription_id:
        return {
            "software": [],
            "drawing_board": [],
            "unknown": [],
        }

    state = _retrieve_subscription_items(
        subscription
    )

    software_items = state["software"]
    drawing_board_items = state[
        "drawing_board"
    ]

    if (
        fail_on_duplicates
        and len(software_items) > 1
    ):
        raise ValueError(
            "Stripe has multiple Encore software items on this "
            "subscription. Repair the subscription before making "
            "another billing change."
        )

    if (
        fail_on_duplicates
        and len(drawing_board_items) > 1
    ):
        raise ValueError(
            "Stripe has multiple Drawing Board items on this "
            "subscription. Repair the subscription before making "
            "another billing change."
        )

    update_fields = []

    software_item_id = (
        stripe_value(
            software_items[0],
            "id",
            "",
        )
        if len(software_items) == 1
        else ""
    )

    drawing_board_item_id = (
        stripe_value(
            drawing_board_items[0],
            "id",
            "",
        )
        if len(drawing_board_items) == 1
        else ""
    )

    if (
        software_item_id
        != subscription.stripe_software_item_id
    ):
        subscription.stripe_software_item_id = (
            software_item_id
        )
        update_fields.append(
            "stripe_software_item_id"
        )

    if (
        drawing_board_item_id
        != subscription.stripe_drawing_board_item_id
    ):
        subscription.stripe_drawing_board_item_id = (
            drawing_board_item_id
        )
        update_fields.append(
            "stripe_drawing_board_item_id"
        )

    if update_fields:
        update_fields.append("updated_at")
        subscription.save(
            update_fields=update_fields
        )

    return state


def _current_subscription_state(subscription):
    return {
        "plan_tier": subscription.plan_tier,
        "student_band": subscription.student_band,
        "drawing_board_enabled": (
            subscription.drawing_board_enabled
        ),
    }


def _next_subscription_state(subscription):
    return {
        "plan_tier": (
            subscription.pending_plan_tier
            or subscription.plan_tier
        ),
        "student_band": (
            subscription.pending_student_band
            or subscription.student_band
        ),
        "drawing_board_enabled": (
            subscription.drawing_board_enabled
            if (
                subscription.pending_drawing_board_enabled
                is None
            )
            else subscription.pending_drawing_board_enabled
        ),
    }


def _apply_stripe_subscription_state(
    subscription,
    *,
    plan_tier,
    student_band,
    drawing_board_enabled,
    proration_behavior="none",
):
    """
    Reconcile Stripe to one explicit Encore billing state.

    Exactly one software item is preserved. Drawing Board is present zero
    or one time according to drawing_board_enabled. Unknown third-party
    Stripe items are left untouched.
    """
    state = reconcile_subscription_item_ids(
        subscription,
        fail_on_duplicates=True,
    )

    if not subscription.stripe_software_item_id:
        raise ValueError(
            "Encore could not identify the Stripe software item."
        )

    software_price = ensure_software_price(
        plan_tier=plan_tier,
        student_band=student_band,
    )

    changes = [
        {
            "id": subscription.stripe_software_item_id,
            "price": software_price.id,
            "quantity": 1,
        }
    ]

    drawing_board_items = state[
        "drawing_board"
    ]

    if drawing_board_enabled:
        drawing_price = ensure_drawing_board_price()

        if subscription.stripe_drawing_board_item_id:
            changes.append(
                {
                    "id": (
                        subscription.stripe_drawing_board_item_id
                    ),
                    "price": drawing_price.id,
                    "quantity": 1,
                }
            )
        else:
            changes.append(
                {
                    "price": drawing_price.id,
                    "quantity": 1,
                }
            )
    else:
        for item in drawing_board_items:
            changes.append(
                {
                    "id": stripe_value(
                        item,
                        "id",
                        "",
                    ),
                    "deleted": True,
                }
            )

    stripe.Subscription.modify(
        subscription.stripe_subscription_id,
        items=changes,
        proration_behavior=proration_behavior,
    )

    return reconcile_subscription_item_ids(
        subscription,
        fail_on_duplicates=True,
    )


def _stage_next_subscription_state(subscription):
    """
    Make Stripe's next recurring configuration match Encore's combined
    pending state without creating prorations.
    """
    if not subscription.stripe_subscription_id:
        return None

    next_state = _next_subscription_state(
        subscription
    )

    return _apply_stripe_subscription_state(
        subscription,
        plan_tier=next_state["plan_tier"],
        student_band=next_state["student_band"],
        drawing_board_enabled=(
            next_state["drawing_board_enabled"]
        ),
        proration_behavior="none",
    )


def _restore_current_stripe_state(subscription):
    """
    Undo any no-proration future staging temporarily so an immediate
    upgrade/add-on proration is calculated from the real current state.
    """
    if not subscription.stripe_subscription_id:
        return None

    current_state = _current_subscription_state(
        subscription
    )

    return _apply_stripe_subscription_state(
        subscription,
        plan_tier=current_state["plan_tier"],
        student_band=current_state["student_band"],
        drawing_board_enabled=(
            current_state["drawing_board_enabled"]
        ),
        proration_behavior="none",
    )


def repair_subscription_items(subscription):
    """
    Explicit one-time repair for malformed Encore Stripe subscriptions.

    This is intentionally manual. It removes duplicate Encore software or
    Drawing Board items, restores the intended current/pending configuration,
    and creates no prorations.
    """
    if not subscription.stripe_subscription_id:
        raise ValueError(
            "This studio does not have a Stripe subscription ID."
        )

    state = _retrieve_subscription_items(
        subscription
    )

    software_items = state["software"]
    drawing_board_items = state[
        "drawing_board"
    ]

    if not software_items:
        raise ValueError(
            "No Encore software item could be identified in Stripe."
        )

    next_state = _next_subscription_state(
        subscription
    )

    software_price = ensure_software_price(
        plan_tier=next_state["plan_tier"],
        student_band=next_state["student_band"],
    )

    software_ids = {
        stripe_value(item, "id", "")
        for item in software_items
    }

    if (
        subscription.stripe_software_item_id
        in software_ids
    ):
        canonical_software = next(
            item
            for item in software_items
            if stripe_value(
                item,
                "id",
                "",
            )
            == subscription.stripe_software_item_id
        )
    else:
        canonical_software = software_items[0]

    canonical_software_id = stripe_value(
        canonical_software,
        "id",
        "",
    )

    changes = [
        {
            "id": canonical_software_id,
            "price": software_price.id,
            "quantity": 1,
        }
    ]

    for item in software_items:
        item_id = stripe_value(
            item,
            "id",
            "",
        )

        if item_id != canonical_software_id:
            changes.append(
                {
                    "id": item_id,
                    "deleted": True,
                }
            )

    if next_state["drawing_board_enabled"]:
        drawing_price = ensure_drawing_board_price()

        if drawing_board_items:
            canonical_drawing = (
                drawing_board_items[0]
            )

            changes.append(
                {
                    "id": stripe_value(
                        canonical_drawing,
                        "id",
                        "",
                    ),
                    "price": drawing_price.id,
                    "quantity": 1,
                }
            )

            for item in drawing_board_items[1:]:
                changes.append(
                    {
                        "id": stripe_value(
                            item,
                            "id",
                            "",
                        ),
                        "deleted": True,
                    }
                )
        else:
            changes.append(
                {
                    "price": drawing_price.id,
                    "quantity": 1,
                }
            )
    else:
        for item in drawing_board_items:
            changes.append(
                {
                    "id": stripe_value(
                        item,
                        "id",
                        "",
                    ),
                    "deleted": True,
                }
            )

    stripe.Subscription.modify(
        subscription.stripe_subscription_id,
        items=changes,
        proration_behavior="none",
    )

    reconcile_subscription_item_ids(
        subscription,
        fail_on_duplicates=True,
    )

    has_pending_change = bool(
        subscription.pending_plan_tier
        or subscription.pending_student_band
        or (
            subscription.pending_drawing_board_enabled
            is not None
        )
    )

    if not has_pending_change:
        subscription.current_monthly_price = (
            subscription_price(
                subscription.plan_tier,
                subscription.student_band,
                drawing_board=(
                    subscription.drawing_board_enabled
                ),
            )
            or subscription.current_monthly_price
        )

        subscription.save(
            update_fields=[
                "current_monthly_price",
                "updated_at",
            ]
        )

    return _retrieve_subscription_items(
        subscription
    )


def create_signup_intent(cleaned):
    band = "0_100"

    monthly_price = subscription_price(
        cleaned["plan_tier"],
        band,
        drawing_board=cleaned[
            "drawing_board_enabled"
        ],
    )

    return StudioSignupIntent.objects.create(
        owner_email=cleaned[
            "email"
        ],
        owner_first_name=cleaned[
            "first_name"
        ],
        owner_last_name=cleaned[
            "last_name"
        ],
        owner_username=(
            f"owner_{uuid4().hex[:16]}"
        ),
        owner_password_hash=make_password(
            cleaned["password"]
        ),
        studio_name=cleaned[
            "studio_name"
        ],
        studio_email=cleaned.get(
            "studio_email",
            "",
        ),
        studio_phone=cleaned.get(
            "studio_phone",
            "",
        ),
        plan_tier=cleaned[
            "plan_tier"
        ],
        drawing_board_enabled=cleaned[
            "drawing_board_enabled"
        ],
        student_band=band,
        monthly_price=monthly_price,
        terms_version=TERMS_VERSION,
        terms_accepted_at=timezone.now(),
    )


def create_checkout_session(
    request,
    intent,
):
    configure_stripe()

    software_price = ensure_software_price(
        plan_tier=intent.plan_tier,
        student_band=intent.student_band,
    )

    line_items = [
        {
            "price": software_price.id,
            "quantity": 1,
        }
    ]

    if intent.drawing_board_enabled:
        drawing_board_price = (
            ensure_drawing_board_price()
        )

        line_items.append(
            {
                "price": (
                    drawing_board_price.id
                ),
                "quantity": 1,
            }
        )

    success_url = request.build_absolute_uri(
        reverse(
            "accounts:registration_success",
        )
    )

    success_url += (
        "?session_id={CHECKOUT_SESSION_ID}"
    )

    cancel_url = request.build_absolute_uri(
        reverse(
            "accounts:register",
        )
    )

    session = stripe.checkout.Session.create(
        mode="subscription",
        customer_email=intent.owner_email,
        line_items=line_items,
        success_url=success_url,
        cancel_url=cancel_url,
        allow_promotion_codes=False,
        metadata={
            "encore_signup_intent_id": (
                str(
                    intent.pk
                )
            ),
        },
        subscription_data={
            "metadata": {
                "encore_signup_intent_id": (
                    str(
                        intent.pk
                    )
                ),
                "plan_tier": intent.plan_tier,
                "student_band": (
                    intent.student_band
                ),
            },
        },
    )

    intent.stripe_checkout_session_id = (
        session.id
    )

    intent.status = (
        StudioSignupIntent.Status.CHECKOUT_CREATED
    )

    intent.save(
        update_fields=[
            "stripe_checkout_session_id",
            "status",
            "updated_at",
        ]
    )

    return session


def _unique_studio_slug(name):
    base = slugify(
        name
    )[:42] or "studio"

    candidate = base
    counter = 2

    while Studio.objects.filter(
        slug=candidate,
    ).exists():
        candidate = (
            f"{base}-{counter}"
        )

        counter += 1

    return candidate


def _stripe_datetime(value):
    if not value:
        return None

    return datetime.fromtimestamp(
        value,
        tz=dt_timezone.utc,
    )


@transaction.atomic
def finalize_paid_signup(
    intent,
    checkout_session=None,
):
    if (
        intent.status
        == StudioSignupIntent.Status.PAID
        and intent.studio_id
    ):
        return intent.studio

    configure_stripe()

    if checkout_session is None:
        checkout_session = (
            stripe.checkout.Session.retrieve(
                intent.stripe_checkout_session_id,
                expand=[
                    "subscription",
                    "subscription.items.data.price",
                ],
            )
        )

    if stripe_value(
        checkout_session,
        "payment_status",
    ) != "paid":
        raise ValueError(
            "Checkout has not been paid."
        )

    User = get_user_model()

    if User.objects.filter(
        email=intent.owner_email,
    ).exists():
        raise ValueError(
            "An Encore account already exists for this email."
        )

    user = User(
        username=intent.owner_username,
        email=intent.owner_email,
        first_name=intent.owner_first_name,
        last_name=intent.owner_last_name,
        is_active=True,
        email_verification_required=True,
    )

    user.password = intent.owner_password_hash
    user.save()

    studio = Studio.objects.create(
        name=intent.studio_name,
        slug=_unique_studio_slug(
            intent.studio_name
        ),
        email=(
            intent.studio_email
            or intent.owner_email
        ),
        phone=intent.studio_phone,
        is_active=True,
    )

    StudioSettings.objects.get_or_create(
        studio=studio,
    )

    StudioMembership.objects.create(
        studio=studio,
        user=user,
        role=(
            StudioMembership.Role.ADMINISTRATOR
        ),
        is_active=True,
        onboarding_tour_status=(
            StudioMembership.TourStatus.NOT_STARTED
        ),
        onboarding_tour_step=0,
    )

    stripe_subscription = stripe_value(
        checkout_session,
        "subscription",
    )

    if isinstance(
        stripe_subscription,
        str,
    ):
        stripe_subscription = (
            stripe.Subscription.retrieve(
                stripe_subscription,
                expand=[
                    "items.data.price",
                ],
            )
        )

    software_item_id = ""
    drawing_board_item_id = ""

    for item in stripe_subscription[
        "items"
    ]["data"]:
        kind = _subscription_item_kind(
            item
        )

        if kind == "software":
            if software_item_id:
                raise ValueError(
                    "Stripe returned multiple Encore software items "
                    "during signup."
                )

            software_item_id = item["id"]

        elif kind == "drawing_board":
            if drawing_board_item_id:
                raise ValueError(
                    "Stripe returned multiple Drawing Board items "
                    "during signup."
                )

            drawing_board_item_id = (
                item["id"]
            )

    if not software_item_id:
        raise ValueError(
            "Encore could not identify the software subscription "
            "item returned by Stripe."
        )

    subscription = (
        StudioSubscription.objects.create(
            studio=studio,
            plan_tier=intent.plan_tier,
            student_band=intent.student_band,
            drawing_board_enabled=(
                intent.drawing_board_enabled
            ),
            current_monthly_price=(
                intent.monthly_price
            ),
            status=(
                StudioSubscription.Status.ACTIVE
            ),
            stripe_customer_id=(
                stripe_value(
                    checkout_session,
                    "customer",
                    "",
                )
            ),
            stripe_subscription_id=(
                stripe_subscription["id"]
            ),
            stripe_software_item_id=(
                software_item_id
            ),
            stripe_drawing_board_item_id=(
                drawing_board_item_id
            ),
            current_period_start=(
                _stripe_datetime(
                    stripe_value(
                        stripe_subscription,
                        "current_period_start",
                    )
                )
            ),
            current_period_end=(
                _stripe_datetime(
                    stripe_value(
                        stripe_subscription,
                        "current_period_end",
                    )
                )
            ),
        )
    )

    intent.status = (
        StudioSignupIntent.Status.PAID
    )

    intent.studio = studio

    intent.stripe_customer_id = (
        subscription.stripe_customer_id
    )

    intent.stripe_subscription_id = (
        subscription.stripe_subscription_id
    )

    intent.save(
        update_fields=[
            "status",
            "studio",
            "stripe_customer_id",
            "stripe_subscription_id",
            "updated_at",
        ]
    )

    intent_id = intent.pk
    transaction.on_commit(
        lambda: _dispatch_signup_communications(intent_id)
    )

    return studio


def _dispatch_signup_communications(intent_id):
    try:
        from accounts.registration_services import (
            ensure_signup_communications,
        )

        intent = (
            StudioSignupIntent.objects
            .select_related("studio")
            .filter(pk=intent_id)
            .first()
        )
        if intent is not None:
            ensure_signup_communications(intent)
    except Exception:
        import logging

        logging.getLogger(__name__).exception(
            "Unable to send Encore signup communications for intent %s",
            intent_id,
        )


def create_subscription_notice(
    subscription,
    *,
    notice_type,
    title,
    message,
):
    return SubscriptionNotice.objects.create(
        studio=subscription.studio,
        notice_type=notice_type,
        title=title,
        message=message,
    )


def send_subscription_email(
    studio,
    *,
    subject,
    message,
):
    try:
        from communications.email_service import (
            send_email,
        )
    except ImportError:
        return None

    recipient = (
        studio.email
        or (
            studio.memberships
            .filter(
                role="administrator",
                is_active=True,
            )
            .select_related(
                "user",
            )
            .values_list(
                "user__email",
                flat=True,
            )
            .first()
        )
    )

    if not recipient:
        return None

    return send_email(
        to=[
            recipient,
        ],
        subject=subject,
        html_body=(
            f"<p>{message}</p>"
        ),
        text_body=message,
        tags={
            "message_type": (
                "subscription"
            ),
            "studio_id": (
                studio.pk
            ),
        },
    )


def evaluate_student_band_change(
    subscription,
):
    count = subscription.studio.students.count()

    new_band = student_band_for_count(
        count
    )

    if new_band == "custom":
        return False

    # If the studio returned to the currently billed band before renewal,
    # cancel any previously scheduled band change.
    if new_band == subscription.student_band:
        if subscription.pending_student_band:
            subscription.pending_student_band = ""
            subscription.save(
                update_fields=[
                    "pending_student_band",
                    "updated_at",
                ]
            )

            _stage_next_subscription_state(
                subscription
            )

            return "cancelled"

        return False

    if (
        new_band
        == subscription.pending_student_band
    ):
        return False

    old_price = (
        subscription.current_monthly_price
    )

    subscription.pending_student_band = (
        new_band
    )

    subscription.save(
        update_fields=[
            "pending_student_band",
            "updated_at",
        ]
    )

    next_state = _next_subscription_state(
        subscription
    )

    new_price = subscription_price(
        next_state["plan_tier"],
        next_state["student_band"],
        drawing_board=(
            next_state["drawing_board_enabled"]
        ),
    )

    create_subscription_notice(
        subscription,
        notice_type=(
            SubscriptionNotice.NoticeType.PRICE_CHANGE
        ),
        title="Subscription price changing",
        message=(
            f"Encore now counts {count} student records. "
            f"At your next billing cycle, your student band will "
            f"change from {PRICE_CATALOG[subscription.student_band]['label']} "
            f"to {PRICE_CATALOG[new_band]['label']}. "
            f"Your monthly subscription will change from "
            f"${old_price} to ${new_price}."
        ),
    )

    send_subscription_email(
        subscription.studio,
        subject=(
            "Encore subscription price change"
        ),
        message=(
            f"Your studio now has {count} student records. "
            f"Your Encore subscription will move to the "
            f"{PRICE_CATALOG[new_band]['label']} student band "
            f"at your next billing cycle. "
            f"Your new monthly price will be ${new_price}."
        ),
    )

    _stage_next_subscription_state(
        subscription
    )

    return True


def request_plan_change(
    subscription,
    new_plan,
):
    current_plan = subscription.plan_tier
    pending_plan = subscription.pending_plan_tier

    # Selecting the actual current plan while a downgrade is pending
    # means "cancel my scheduled downgrade."
    if (
        new_plan == current_plan
        and pending_plan
    ):
        subscription.pending_plan_tier = ""
        subscription.save(
            update_fields=[
                "pending_plan_tier",
                "updated_at",
            ]
        )

        _stage_next_subscription_state(
            subscription
        )

        return "downgrade_cancelled"

    if (
        new_plan == current_plan
        and not pending_plan
    ):
        return "unchanged"

    current_rank = {
        "essentials": 1,
        "pro": 2,
    }

    is_upgrade = (
        current_rank[new_plan]
        > current_rank[current_plan]
    )

    configure_stripe()

    if is_upgrade:
        # Stripe may already be staged to a future student band or add-on
        # configuration. Restore the real current state first so Stripe's
        # proration is based on what the customer is actually paying now.
        _restore_current_stripe_state(
            subscription
        )

        immediate_state = {
            "plan_tier": new_plan,
            "student_band": (
                subscription.student_band
            ),
            "drawing_board_enabled": (
                subscription.drawing_board_enabled
            ),
        }

        _apply_stripe_subscription_state(
            subscription,
            plan_tier=immediate_state["plan_tier"],
            student_band=immediate_state["student_band"],
            drawing_board_enabled=(
                immediate_state[
                    "drawing_board_enabled"
                ]
            ),
            proration_behavior="always_invoice",
        )

        subscription.plan_tier = new_plan
        subscription.pending_plan_tier = ""
        subscription.current_monthly_price = (
            subscription_price(
                new_plan,
                subscription.student_band,
                drawing_board=(
                    subscription.drawing_board_enabled
                ),
            )
        )

        subscription.save(
            update_fields=[
                "plan_tier",
                "current_monthly_price",
                "pending_plan_tier",
                "updated_at",
            ]
        )

        # Re-stage any remaining future band/add-on change after the
        # immediate upgrade has been prorated correctly.
        _stage_next_subscription_state(
            subscription
        )

        return "upgraded"

    # Downgrades remain active through the paid period. Store the desired
    # future plan and stage Stripe's next recurring configuration without
    # creating a credit/proration today.
    subscription.pending_plan_tier = new_plan
    subscription.save(
        update_fields=[
            "pending_plan_tier",
            "updated_at",
        ]
    )

    _stage_next_subscription_state(
        subscription
    )

    return "downgrade_scheduled"


def request_drawing_board_change(
    subscription,
    enabled,
):
    configure_stripe()

    current_enabled = (
        subscription.drawing_board_enabled
    )

    pending_enabled = (
        subscription.pending_drawing_board_enabled
    )

    # User has Drawing Board now, scheduled its removal, then changes
    # their mind. Cancel the pending removal with no charge.
    if (
        current_enabled
        and enabled
        and pending_enabled is False
    ):
        subscription.pending_drawing_board_enabled = (
            None
        )

        subscription.save(
            update_fields=[
                "pending_drawing_board_enabled",
                "updated_at",
            ]
        )

        _stage_next_subscription_state(
            subscription
        )

        return "removal_cancelled"

    if enabled == current_enabled:
        return "unchanged"

    if enabled:
        # Adding an add-on is immediate and prorated. Temporarily restore
        # the actual current Stripe state so any separately scheduled
        # plan/student-band changes do not contaminate the proration.
        _restore_current_stripe_state(
            subscription
        )

        _apply_stripe_subscription_state(
            subscription,
            plan_tier=subscription.plan_tier,
            student_band=subscription.student_band,
            drawing_board_enabled=True,
            proration_behavior="always_invoice",
        )

        subscription.drawing_board_enabled = True
        subscription.pending_drawing_board_enabled = (
            None
        )
        subscription.current_monthly_price = (
            subscription_price(
                subscription.plan_tier,
                subscription.student_band,
                drawing_board=True,
            )
        )

        subscription.save(
            update_fields=[
                "drawing_board_enabled",
                "pending_drawing_board_enabled",
                "current_monthly_price",
                "stripe_drawing_board_item_id",
                "updated_at",
            ]
        )

        _stage_next_subscription_state(
            subscription
        )

        return "added"

    # Removal is next-cycle only. Access remains active in Encore during
    # the paid period, while Stripe is staged to omit the add-on next time.
    subscription.pending_drawing_board_enabled = (
        False
    )

    subscription.save(
        update_fields=[
            "pending_drawing_board_enabled",
            "updated_at",
        ]
    )

    _stage_next_subscription_state(
        subscription
    )

    return "removal_scheduled"


def cancel_subscription_at_period_end(
    subscription,
):
    configure_stripe()

    stripe.Subscription.modify(
        subscription.stripe_subscription_id,
        cancel_at_period_end=True,
    )

    subscription.cancel_at_period_end = True

    subscription.status = (
        StudioSubscription.Status.CANCEL_AT_PERIOD_END
    )

    subscription.save(
        update_fields=[
            "cancel_at_period_end",
            "status",
            "updated_at",
        ]
    )


def resume_subscription(
    subscription,
):
    configure_stripe()

    stripe.Subscription.modify(
        subscription.stripe_subscription_id,
        cancel_at_period_end=False,
    )

    subscription.cancel_at_period_end = False

    subscription.status = (
        StudioSubscription.Status.ACTIVE
    )

    subscription.save(
        update_fields=[
            "cancel_at_period_end",
            "status",
            "updated_at",
        ]
    )


def apply_renewal_state(
    subscription,
):
    changed = False

    if subscription.pending_plan_tier:
        subscription.plan_tier = (
            subscription.pending_plan_tier
        )

        subscription.pending_plan_tier = ""

        changed = True

    if subscription.pending_student_band:
        subscription.student_band = (
            subscription.pending_student_band
        )

        subscription.pending_student_band = ""

        changed = True

    if (
        subscription.pending_drawing_board_enabled
        is not None
    ):
        subscription.drawing_board_enabled = (
            subscription.pending_drawing_board_enabled
        )

        subscription.pending_drawing_board_enabled = None

        if not subscription.drawing_board_enabled:
            subscription.stripe_drawing_board_item_id = ""

        changed = True

    if changed:
        subscription.current_monthly_price = (
            subscription_price(
                subscription.plan_tier,
                subscription.student_band,
                drawing_board=(
                    subscription.drawing_board_enabled
                ),
            )
            or subscription.current_monthly_price
        )

        subscription.save()

    return changed
