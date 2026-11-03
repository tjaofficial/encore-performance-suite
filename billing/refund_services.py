"""Refund only an eligible Stripe-funded, current-month, allocated tuition charge.

Refund reconciliation replaces a payment allocation with an equally sized credit on
that same charge: the family is not invoiced again for an administrator-granted refund.
"""
from decimal import Decimal
from uuid import uuid4

import stripe
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django.core.exceptions import ValidationError

from .models import PaymentRefund, PaymentAllocation, Credit, CreditAllocation, StudioSubscription, FamilyAutoPayProfile
from .stripe_environment import connected_account_for_subscription
from .subscription_services import configure_stripe, stripe_value, stripe_metadata

PENDING = (PaymentRefund.Status.PROCESSING, PaymentRefund.Status.PENDING, PaymentRefund.Status.SUCCEEDED)


def available_for_refund(payment, charge):
    allocation = PaymentAllocation.objects.filter(payment=payment, charge=charge).first()
    if not allocation:
        return Decimal("0.00")
    # allocation is reduced when a successful refund is reconciled, so count only unsettled holds
    outstanding_holds = PaymentRefund.objects.filter(payment=payment, charge=charge, status__in=[PaymentRefund.Status.PROCESSING, PaymentRefund.Status.PENDING]).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    return max(Decimal("0.00"), allocation.amount - outstanding_holds)


def eligible_allocations(account):
    today = timezone.localdate()
    return (PaymentAllocation.objects.select_related("payment", "charge", "charge__student")
            .filter(payment__account=account, payment__status="succeeded", charge__charge_type="tuition", charge__status="paid")
            .order_by("-payment__paid_at", "-pk"))


def request_refund(*, account, payment, charge, amount, reason, notes, admin):
    if payment.account_id != account.id or charge.account_id != account.id:
        raise ValidationError("Payment and tuition charge must belong to this family.")
    if payment.status != "succeeded" or not payment.external_reference.startswith("pi_"):
        raise ValidationError("Only completed Stripe payments can be refunded to the original method.")
    if charge.charge_type != "tuition" or charge.status != "paid":
        raise ValidationError("Choose a paid tuition charge.")
    day = charge.service_period_start or charge.due_date
    today = timezone.localdate()
    if not day or (day.year, day.month) != (today.year, today.month):
        raise ValidationError("This refund tool is limited to current-month tuition.")
    if amount <= 0 or amount != amount.quantize(Decimal(".01")):
        raise ValidationError("Enter a valid positive amount in cents.")
    try:
        subscription = StudioSubscription.objects.get(studio=account.studio)
    except StudioSubscription.DoesNotExist as exc:
        raise ValidationError("This studio must activate Stripe Connect before issuing refunds.") from exc
    connected_id = connected_account_for_subscription(subscription)
    with transaction.atomic():
        # Serialize requests for one payment; do not allow overlapping refunds.
        payment = type(payment).objects.select_for_update().get(pk=payment.pk)
        if amount > available_for_refund(payment, charge):
            raise ValidationError("Amount exceeds the remaining refundable allocation.")
        if PaymentRefund.objects.filter(payment=payment, status=PaymentRefund.Status.PROCESSING).exists():
            raise ValidationError("A refund request for this payment is still processing.")
        refund = PaymentRefund.objects.create(payment=payment, charge=charge, amount=amount,
            reason=reason, notes=notes, requested_by=admin, stripe_account_id=connected_id,
            idempotency_key=f"encore-refund-{uuid4().hex}")
    # Never hold a database transaction open during a network call.
    try:
        configure_stripe()
        intent = stripe.PaymentIntent.retrieve(payment.external_reference, stripe_account=connected_id)
        if stripe_value(intent, "status") != "succeeded":
            raise ValidationError("Stripe does not show this payment as succeeded.")
        metadata = stripe_metadata(intent)
        family_id = str(metadata.get("family_account_id", "")).strip()
        owner_customer = stripe_value(intent, "customer", "")
        known_customers = set(FamilyAutoPayProfile.objects.filter(account=account, connected_account_id=connected_id)
                              .exclude(stripe_customer_id="").values_list("stripe_customer_id", flat=True))
        if family_id != str(account.pk) and (not owner_customer or owner_customer not in known_customers):
            raise ValidationError("Stripe payment cannot be verified as belonging to this family. No refund was issued.")
        if int(stripe_value(intent, "amount_received", 0) or 0) < int(payment.amount * 100):
            raise ValidationError("Stripe payment amount does not match Encore's payment record.")
        result = stripe.Refund.create(payment_intent=payment.external_reference,
            amount=int(amount * 100), reason="requested_by_customer",
            metadata={"encore_refund_id": str(refund.pk), "studio_id": str(account.studio_id)},
            stripe_account=connected_id, idempotency_key=refund.idempotency_key)
    except stripe.error.StripeError as exc:
        # Treat failures conservatively. If AWS/Stripe network dropped after creation,
        # issuing another refund with a different key would risk duplicate money out.
        ambiguous = isinstance(exc, (stripe.error.APIConnectionError, stripe.error.APIError, stripe.error.RateLimitError))
        PaymentRefund.objects.filter(pk=refund.pk).update(
            status=PaymentRefund.Status.PENDING if ambiguous else PaymentRefund.Status.FAILED,
            last_error=str(exc))
        raise ValidationError("Stripe outcome needs verification; do not retry." if ambiguous else
                              "Stripe rejected the refund. Check refund history.") from exc
    except Exception as exc:
        # Payment verification/network ambiguity: hold the request for reconciliation, never auto-retry with a new key.
        PaymentRefund.objects.filter(pk=refund.pk).update(status=PaymentRefund.Status.PENDING, last_error=str(exc))
        raise ValidationError("Refund outcome needs verification in Stripe; do not retry until reconciled.") from exc
    return reconcile_refund(refund.pk, result, connected_id)


def reconcile_refund(refund_id, stripe_obj, connected_id):
    with transaction.atomic():
        refund = PaymentRefund.objects.select_for_update().select_related("payment", "charge").get(pk=refund_id)
        if refund.stripe_account_id != connected_id:
            raise ValidationError("Wrong studio Stripe account.")
        provider_id = stripe_value(stripe_obj, "id", "")
        if refund.stripe_refund_id and refund.stripe_refund_id != provider_id:
            raise ValidationError("Stripe refund ID mismatch.")
        if stripe_value(stripe_obj, "payment_intent", refund.payment.external_reference) != refund.payment.external_reference:
            raise ValidationError("Stripe refund belongs to a different payment.")
        if int(stripe_value(stripe_obj, "amount", 0)) != int(refund.amount * 100):
            raise ValidationError("Stripe refund amount does not match the approved amount.")
        state = stripe_value(stripe_obj, "status", "pending")
        if state not in ("succeeded", "pending", "failed", "canceled", "requires_action"):
            state = "pending"
        refund.stripe_refund_id = provider_id or refund.stripe_refund_id
        refund.status = "pending" if state == "requires_action" else state
        if refund.ledger_applied and state in ("failed", "canceled"):
            refund.last_error = "ALERT: Stripe reversed a reconciled refund. Manual ledger review required."
            refund.save(update_fields=["last_error", "updated_at"])
            raise ValidationError("A settled refund was reversed. Manual finance review required.")
        if state == "succeeded" and not refund.ledger_applied:
            allocation = PaymentAllocation.objects.select_for_update().get(payment=refund.payment, charge=refund.charge)
            if allocation.amount < refund.amount:
                raise ValidationError("Allocation mismatch. Reconciliation requires review.")
            if allocation.amount == refund.amount:
                allocation.delete()
            else:
                allocation.amount -= refund.amount
                allocation.save(update_fields=["amount"])
            credit = Credit.objects.create(account=refund.payment.account, student=refund.charge.student,
                credit_type=Credit.CreditType.REFUND, amount=refund.amount,
                description=f"Refund adjustment #{refund.pk}: {refund.charge.description}",
                notes=f"Refunded to original payment method; {refund.reason}. {refund.notes}")
            CreditAllocation.objects.create(credit=credit, charge=refund.charge, amount=refund.amount)
            refund.ledger_applied = True
            from .email_notifications import queue_billing_notice
            account = refund.payment.account
            event_key = f"refund:{refund.pk}"
            subject = f"{account.studio.name} — Tuition refund"
            body = (f"A tuition refund of ${refund.amount:.2f} has been issued for {refund.charge.description}. "
                    "The time needed to appear on the original payment method depends on the bank.")
            transaction.on_commit(lambda: queue_billing_notice(account, "refund", event_key, subject, body))
        refund.save()
        return refund


def reconcile_from_webhook(obj, connected_account_id):
    provider_id = stripe_value(obj, "id", "")
    meta = stripe_value(obj, "metadata", {}) or {}
    refund_id = stripe_value(meta, "encore_refund_id", "")
    record = PaymentRefund.objects.filter(pk=refund_id).first() if str(refund_id).isdigit() else PaymentRefund.objects.filter(stripe_refund_id=provider_id).first()
    if record is None:
        return
    return reconcile_refund(record.pk, obj, connected_account_id)
