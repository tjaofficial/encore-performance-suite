from datetime import timedelta
from decimal import Decimal

import stripe
from django.conf import settings
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from billing.models import StudioSubscription
from enrollments.models import Enrollment

from .models import (
    PublicRegistrationSession,
    RegistrationClassHold,
)
from .services import (
    finalize_public_registration,
    registration_pricing_snapshot,
)
from .security import registration_identity_verified
from .policy_services import registration_policies_satisfied


HOLD_MINUTES = 20


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


def connected_subscription_for_registration(
    registration_session,
):
    subscription = (
        StudioSubscription.objects
        .filter(
            studio=registration_session.studio,
        )
        .first()
    )

    if subscription is None:
        return None

    if (
        not subscription.payments_connected
        or not subscription.stripe_connected_account_id
        or not subscription.stripe_connect_charges_enabled
    ):
        return None

    return subscription


@transaction.atomic
def reserve_registration_classes(
    registration_session,
):
    now = timezone.now()
    expires_at = now + timedelta(
        minutes=HOLD_MINUTES
    )

    RegistrationClassHold.objects.filter(
        expires_at__lte=now,
        is_active=True,
    ).update(
        is_active=False,
    )

    session = (
        PublicRegistrationSession.objects
        .select_for_update()
        .get(pk=registration_session.pk)
    )

    selected = list(
        session.selected_classes
        .select_related("season")
        .order_by("pk")
    )

    raw_student_data = session.student_data or {}
    assignment_counts = {}
    if isinstance(raw_student_data.get("assignments"), dict):
        for values in raw_student_data.get("assignments", {}).values():
            if not isinstance(values, list):
                continue
            for value in values:
                if str(value).isdigit():
                    class_id = int(value)
                    assignment_counts[class_id] = assignment_counts.get(class_id, 0) + 1

    waitlisted_ids = set()
    settings_obj = getattr(
        session.studio,
        "settings",
        None,
    )
    allow_waitlist = (
        settings_obj.allow_waitlist_requests
        if settings_obj is not None
        else True
    )

    for class_instance in selected:
        active_enrollment_count = (
            Enrollment.objects
            .filter(
                class_instance=class_instance,
                status=Enrollment.Status.ACTIVE,
            )
            .count()
        )

        other_holds = (
            RegistrationClassHold.objects
            .filter(
                class_instance=class_instance,
                is_active=True,
                expires_at__gt=now,
            )
            .exclude(
                registration_session=session,
            )
            .count()
        )

        seats_needed = max(assignment_counts.get(class_instance.pk, 1), 1)
        has_capacity = (
            class_instance.capacity <= 0
            or (
                active_enrollment_count
                + other_holds
                + seats_needed
                <= class_instance.capacity
            )
        )

        if not has_capacity:
            if allow_waitlist:
                waitlisted_ids.add(
                    class_instance.pk
                )
                RegistrationClassHold.objects.filter(
                    registration_session=session,
                    class_instance=class_instance,
                ).update(
                    is_active=False,
                )
                continue

            raise ValueError(
                (
                    f"{class_instance.name} filled before checkout. "
                    "Go back and choose another class."
                )
            )

        hold, _created = (
            RegistrationClassHold.objects
            .update_or_create(
                registration_session=session,
                class_instance=class_instance,
                defaults={
                    "expires_at": expires_at,
                    "is_active": True,
                },
            )
        )

    snapshot = registration_pricing_snapshot(
        session,
        waitlisted_class_ids=waitlisted_ids,
    )

    return snapshot


def payment_amount_from_snapshot(snapshot):
    return Decimal(
        str(
            snapshot.get(
                "due_today",
                "0.00",
            )
        )
    )


def prepare_registration_payment(
    request,
    registration_session,
):
    if not registration_identity_verified(registration_session):
        raise ValueError(
            "Verify the registration email before starting payment."
        )

    if not registration_policies_satisfied(registration_session):
        raise ValueError(
            "Review and accept the required registration policies before starting payment."
        )

    if (
        registration_session.status
        not in {
            PublicRegistrationSession.Status.READY_FOR_PAYMENT,
            PublicRegistrationSession.Status.PAYMENT_PENDING,
        }
    ):
        raise ValueError(
            "This registration is not ready for payment."
        )

    from .approval_codes import validate_session as validate_class_codes
    validate_class_codes(registration_session)

    snapshot = reserve_registration_classes(
        registration_session
    )

    amount = payment_amount_from_snapshot(
        snapshot
    )

    if amount <= Decimal("0.00"):
        return {
            "amount": amount,
            "client_secret": "",
            "connected_account_id": "",
            "payment_intent_id": "",
        }

    subscription = connected_subscription_for_registration(
        registration_session
    )

    if subscription is None:
        raise ValueError(
            (
                "This studio has not finished connecting Stripe "
                "for family payments."
            )
        )

    configure_stripe()

    amount_cents = int(
        amount * 100
    )

    metadata = {
        "encore_registration_session_id": str(
            registration_session.pk
        ),
        "encore_registration_token": str(
            registration_session.token
        ),
        "encore_studio_id": str(
            registration_session.studio_id
        ),
    }

    payment_intent = None

    if registration_session.stripe_payment_intent_id:
        try:
            existing = stripe.PaymentIntent.retrieve(
                registration_session.stripe_payment_intent_id,
                stripe_account=(
                    subscription.stripe_connected_account_id
                ),
            )

            existing_status = stripe_value(
                existing,
                "status",
                "",
            )

            if existing_status == "succeeded":
                raise ValueError('Payment has already succeeded. Complete the existing registration; do not pay again.')
            if existing_status not in {
                "succeeded",
                "canceled",
            }:
                payment_intent = stripe.PaymentIntent.modify(
                    existing.id,
                    amount=amount_cents,
                    receipt_email=registration_session.contact_email,
                    metadata=metadata,
                    stripe_account=(
                        subscription.stripe_connected_account_id
                    ),
                )
        except stripe.error.StripeError:
            payment_intent = None

    if payment_intent is None:
        payment_intent = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency="usd",
            payment_method_types=[
                "card",
            ],
            receipt_email=(
                registration_session.contact_email
            ),
            description=(
                f"{registration_session.studio.name} "
                "class registration"
            ),
            metadata=metadata,
            stripe_account=(
                subscription.stripe_connected_account_id
            ),
            idempotency_key=(
                f"encore-registration-"
                f"{registration_session.token}-"
                f"{amount_cents}"
            ),
        )

    registration_session.stripe_payment_intent_id = (
        payment_intent.id
    )
    registration_session.status = (
        PublicRegistrationSession.Status.PAYMENT_PENDING
    )
    registration_session.save(
        update_fields=[
            "stripe_payment_intent_id",
            "status",
            "pricing_snapshot",
            "updated_at",
        ]
    )

    return {
        "amount": amount,
        "client_secret": stripe_value(
            payment_intent,
            "client_secret",
            "",
        ),
        "connected_account_id": (
            subscription.stripe_connected_account_id
        ),
        "payment_intent_id": payment_intent.id,
    }


def retrieve_registration_payment(
    registration_session,
):
    subscription = connected_subscription_for_registration(
        registration_session
    )

    if (
        subscription is None
        or not registration_session.stripe_payment_intent_id
    ):
        return None

    configure_stripe()

    return stripe.PaymentIntent.retrieve(
        registration_session.stripe_payment_intent_id,
        stripe_account=(
            subscription.stripe_connected_account_id
        ),
    )


def finalize_if_payment_succeeded(
    registration_session,
):
    if not registration_identity_verified(registration_session):
        return None

    if not registration_policies_satisfied(registration_session):
        return None

    payment_intent = retrieve_registration_payment(
        registration_session
    )

    if payment_intent is None:
        return None

    if stripe_value(
        payment_intent,
        "status",
        "",
    ) != "succeeded":
        return None

    amount = (
        Decimal(
            str(
                stripe_value(
                    payment_intent,
                    "amount_received",
                    0,
                )
            )
        )
        / Decimal("100")
    )

    return finalize_public_registration(
        registration_session,
        stripe_payment_intent_id=payment_intent.id,
        paid_amount=amount,
    )


def finalize_from_connect_webhook(
    payment_intent,
    *,
    connected_account_id,
):
    metadata = stripe_value(
        payment_intent,
        "metadata",
        {},
    )

    try:
        metadata = dict(metadata)
    except (TypeError, ValueError):
        metadata = {}

    session_id = metadata.get(
        "encore_registration_session_id"
    )

    if not session_id:
        return None

    registration_session = (
        PublicRegistrationSession.objects
        .filter(pk=session_id)
        .select_related("studio")
        .first()
    )

    if registration_session is None:
        return None

    if not registration_identity_verified(registration_session):
        return None

    if not registration_policies_satisfied(registration_session):
        return None

    subscription = (
        StudioSubscription.objects
        .filter(
            studio=registration_session.studio,
            stripe_connected_account_id=connected_account_id,
        )
        .first()
    )

    if subscription is None:
        return None

    if stripe_value(
        payment_intent,
        "status",
        "",
    ) != "succeeded":
        return None

    amount = (
        Decimal(
            str(
                stripe_value(
                    payment_intent,
                    "amount_received",
                    0,
                )
            )
        )
        / Decimal("100")
    )

    return finalize_public_registration(
        registration_session,
        stripe_payment_intent_id=stripe_value(
            payment_intent,
            "id",
            "",
        ),
        paid_amount=amount,
    )
