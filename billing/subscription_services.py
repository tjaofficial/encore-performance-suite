
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
        "essentials": {
            "software_only": Decimal("79.00"),
            "software_payments": Decimal("59.00"),
        },
        "pro": {
            "software_only": Decimal("99.00"),
            "software_payments": Decimal("79.00"),
        },
    },
    "101_250": {
        "label": "101–250",
        "min": 101,
        "max": 250,
        "essentials": {
            "software_only": Decimal("109.00"),
            "software_payments": Decimal("79.00"),
        },
        "pro": {
            "software_only": Decimal("139.00"),
            "software_payments": Decimal("109.00"),
        },
    },
    "251_500": {
        "label": "251–500",
        "min": 251,
        "max": 500,
        "essentials": {
            "software_only": Decimal("139.00"),
            "software_payments": Decimal("109.00"),
        },
        "pro": {
            "software_only": Decimal("169.00"),
            "software_payments": Decimal("129.00"),
        },
    },
    "501_1000": {
        "label": "501–1,000",
        "min": 501,
        "max": 1000,
        "essentials": {
            "software_only": Decimal("159.00"),
            "software_payments": Decimal("119.00"),
        },
        "pro": {
            "software_only": Decimal("199.00"),
            "software_payments": Decimal("149.00"),
        },
    },
    "1001_2000": {
        "label": "1,001–2,000",
        "min": 1001,
        "max": 2000,
        "essentials": {
            "software_only": Decimal("199.00"),
            "software_payments": Decimal("149.00"),
        },
        "pro": {
            "software_only": Decimal("249.00"),
            "software_payments": Decimal("189.00"),
        },
    },
    "2001_3000": {
        "label": "2,001–3,000",
        "min": 2001,
        "max": 3000,
        "essentials": {
            "software_only": Decimal("239.00"),
            "software_payments": Decimal("179.00"),
        },
        "pro": {
            "software_only": Decimal("299.00"),
            "software_payments": Decimal("229.00"),
        },
    },
    "3001_5000": {
        "label": "3,001–5,000",
        "min": 3001,
        "max": 5000,
        "essentials": {
            "software_only": Decimal("299.00"),
            "software_payments": Decimal("229.00"),
        },
        "pro": {
            "software_only": Decimal("369.00"),
            "software_payments": Decimal("289.00"),
        },
    },
}

DRAWING_BOARD_PRICE = Decimal("39.00")


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
    payment_mode,
    student_band,
    *,
    drawing_board=False,
):
    if student_band == "custom":
        return None

    base = PRICE_CATALOG[
        student_band
    ][plan_tier][payment_mode]

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
                "essentials_software": row[
                    "essentials"
                ]["software_only"],
                "essentials_payments": row[
                    "essentials"
                ]["software_payments"],
                "pro_software": row[
                    "pro"
                ]["software_only"],
                "pro_payments": row[
                    "pro"
                ]["software_payments"],
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
    payment_mode,
    student_band,
):
    return (
        f"encore_{plan_tier}_"
        f"{payment_mode}_{student_band}_monthly"
    )


def ensure_software_price(
    *,
    plan_tier,
    payment_mode,
    student_band,
):
    configure_stripe()

    amount = subscription_price(
        plan_tier,
        payment_mode,
        student_band,
    )

    if amount is None:
        raise ValueError(
            "Custom pricing requires manual setup."
        )

    lookup_key = _price_lookup_key(
        plan_tier=plan_tier,
        payment_mode=payment_mode,
        student_band=student_band,
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
        name="Encore Performance Suite",
        metadata_key="software",
    )

    return stripe.Price.create(
        product=product.id,
        currency="usd",
        unit_amount=int(
            amount
            * 100
        ),
        recurring={
            "interval": "month",
        },
        lookup_key=lookup_key,
        metadata={
            "encore_kind": "software",
            "plan_tier": plan_tier,
            "payment_mode": payment_mode,
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


def create_signup_intent(cleaned):
    band = "0_100"

    monthly_price = subscription_price(
        cleaned["plan_tier"],
        cleaned["payment_mode"],
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
        payment_mode=cleaned[
            "payment_mode"
        ],
        drawing_board_enabled=cleaned[
            "drawing_board_enabled"
        ],
        student_band=band,
        monthly_price=monthly_price,
    )


def create_checkout_session(
    request,
    intent,
):
    configure_stripe()

    software_price = ensure_software_price(
        plan_tier=intent.plan_tier,
        payment_mode=intent.payment_mode,
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
                "payment_mode": intent.payment_mode,
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
        kind = stripe_metadata(
            item["price"]
        ).get(
            "encore_kind"
        )

        if kind == "drawing_board":
            drawing_board_item_id = (
                item["id"]
            )

        else:
            software_item_id = item["id"]

    subscription = (
        StudioSubscription.objects.create(
            studio=studio,
            plan_tier=intent.plan_tier,
            payment_mode=intent.payment_mode,
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

    return studio


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

    if (
        new_band == "custom"
        or new_band == subscription.student_band
        or new_band == subscription.pending_student_band
    ):
        return False

    new_price = subscription_price(
        subscription.plan_tier,
        subscription.payment_mode,
        new_band,
        drawing_board=(
            subscription.drawing_board_enabled
        ),
    )

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

    if subscription.stripe_subscription_id:
        software_price = ensure_software_price(
            plan_tier=subscription.plan_tier,
            payment_mode=subscription.payment_mode,
            student_band=new_band,
        )

        stripe.Subscription.modify(
            subscription.stripe_subscription_id,
            items=[
                {
                    "id": (
                        subscription.stripe_software_item_id
                    ),
                    "price": software_price.id,
                }
            ],
            proration_behavior="none",
        )

    return True


def request_plan_change(
    subscription,
    new_plan,
):
    if new_plan == subscription.plan_tier:
        return "unchanged"

    current_rank = {
        "essentials": 1,
        "pro": 2,
    }

    is_upgrade = (
        current_rank[new_plan]
        > current_rank[
            subscription.plan_tier
        ]
    )

    configure_stripe()

    new_price = ensure_software_price(
        plan_tier=new_plan,
        payment_mode=subscription.payment_mode,
        student_band=subscription.student_band,
    )

    if is_upgrade:
        stripe.Subscription.modify(
            subscription.stripe_subscription_id,
            items=[
                {
                    "id": (
                        subscription.stripe_software_item_id
                    ),
                    "price": new_price.id,
                }
            ],
            proration_behavior="create_prorations",
        )

        subscription.plan_tier = new_plan
        subscription.current_monthly_price = (
            subscription_price(
                new_plan,
                subscription.payment_mode,
                subscription.student_band,
                drawing_board=(
                    subscription.drawing_board_enabled
                ),
            )
        )

        subscription.pending_plan_tier = ""

        subscription.save(
            update_fields=[
                "plan_tier",
                "current_monthly_price",
                "pending_plan_tier",
                "updated_at",
            ]
        )

        return "upgraded"

    stripe.Subscription.modify(
        subscription.stripe_subscription_id,
        items=[
            {
                "id": (
                    subscription.stripe_software_item_id
                ),
                "price": new_price.id,
            }
        ],
        proration_behavior="none",
    )

    subscription.pending_plan_tier = new_plan

    subscription.save(
        update_fields=[
            "pending_plan_tier",
            "updated_at",
        ]
    )

    return "downgrade_scheduled"


def request_drawing_board_change(
    subscription,
    enabled,
):
    configure_stripe()

    if enabled == subscription.drawing_board_enabled:
        return "unchanged"

    if enabled:
        price = ensure_drawing_board_price()

        result = stripe.Subscription.modify(
            subscription.stripe_subscription_id,
            items=[
                {
                    "price": price.id,
                    "quantity": 1,
                }
            ],
            proration_behavior="create_prorations",
            expand=[
                "items.data.price",
            ],
        )

        for item in result[
            "items"
        ]["data"]:
            if (
                stripe_metadata(
                    item["price"]
                ).get(
                    "encore_kind"
                )
                == "drawing_board"
            ):
                subscription.stripe_drawing_board_item_id = (
                    item["id"]
                )
                break

        subscription.drawing_board_enabled = True
        subscription.pending_drawing_board_enabled = None
        subscription.current_monthly_price = (
            subscription_price(
                subscription.plan_tier,
                subscription.payment_mode,
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

        return "added"

    if subscription.stripe_drawing_board_item_id:
        stripe.Subscription.modify(
            subscription.stripe_subscription_id,
            items=[
                {
                    "id": (
                        subscription.stripe_drawing_board_item_id
                    ),
                    "deleted": True,
                }
            ],
            proration_behavior="none",
        )

    subscription.pending_drawing_board_enabled = False

    subscription.save(
        update_fields=[
            "pending_drawing_board_enabled",
            "updated_at",
        ]
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

    if subscription.pending_payment_mode:
        subscription.payment_mode = (
            subscription.pending_payment_mode
        )

        subscription.pending_payment_mode = ""

        changed = True

    if changed:
        subscription.current_monthly_price = (
            subscription_price(
                subscription.plan_tier,
                subscription.payment_mode,
                subscription.student_band,
                drawing_board=(
                    subscription.drawing_board_enabled
                ),
            )
            or subscription.current_monthly_price
        )

        subscription.save()

    return changed
