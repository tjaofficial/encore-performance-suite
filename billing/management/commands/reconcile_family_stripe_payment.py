"""Reconcile an already-succeeded Connect PaymentIntent; NEVER initiate a charge.

Usage: python manage.py reconcile_family_stripe_payment ACCOUNT_ID PI_ID [--apply]
Read-only unless --apply. Strict family/customer/method and amount checks are mandatory.
"""
from decimal import Decimal
import stripe
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from billing.models import FamilyAccount, FamilyAutoPayProfile, Payment
from billing.parent_payment_services import finalize_family_balance_payment
from billing.stripe_environment import connected_account_for_subscription, stripe_mode
from billing.subscription_services import configure_stripe, stripe_metadata, stripe_value


class Command(BaseCommand):
    help = "Verify and reconcile a succeeded family Stripe PaymentIntent (no new debit)."

    def add_arguments(self, parser):
        parser.add_argument("account_id", type=int)
        parser.add_argument("payment_intent_id")
        parser.add_argument("--apply", action="store_true", help="Record verified Stripe payment in Encore; does not charge Stripe")

    def handle(self, *args, **options):
        account_id = options["account_id"]
        pi_id = options["payment_intent_id"].strip()
        if not pi_id.startswith("pi_"):
            raise CommandError("Expected a Stripe PaymentIntent ID (pi_...).")
        account = FamilyAccount.objects.select_related("studio").filter(pk=account_id).first()
        if account is None:
            raise CommandError("Family account not found.")
        subscription = getattr(account.studio, "subscription", None)
        if subscription is None:
            raise CommandError("Studio has no Stripe subscription configuration.")
        profile = FamilyAutoPayProfile.objects.filter(account=account, mode=stripe_mode()).first()
        if not profile or not profile.stripe_customer_id or not profile.stripe_payment_method_id:
            raise CommandError("No saved family Stripe customer and payment method.")
        connect_id = connected_account_for_subscription(subscription)
        if connect_id != profile.connected_account_id:
            raise CommandError("Connected account mismatch.")
        configure_stripe()
        try:
            pi = stripe.PaymentIntent.retrieve(pi_id, stripe_account=connect_id)
        except stripe.error.StripeError as exc:
            raise CommandError(f"Unable to retrieve PaymentIntent: {exc}") from exc
        status = stripe_value(pi, "status", "")
        cents = stripe_value(pi, "amount_received", 0) or 0
        metadata = stripe_metadata(pi)
        if status != "succeeded" or cents <= 0 or stripe_value(pi, "currency") != "usd":
            raise CommandError("PaymentIntent is not a succeeded USD payment with money received.")
        if stripe_value(pi, "customer") != profile.stripe_customer_id:
            raise CommandError("Stripe customer does not match this family.")
        if stripe_value(pi, "payment_method") != profile.stripe_payment_method_id:
            raise CommandError("Stripe payment method does not match this family's saved method.")
        for key, value in (("studio_id", account.studio_id), ("family_account_id", account.pk), ("family_id", account.family_id)):
            if metadata.get(key) and str(metadata[key]) != str(value):
                raise CommandError(f"Conflicting Stripe metadata: {key}.")
        if metadata.get("encore_kind") and metadata["encore_kind"] != "family_balance_payment":
            raise CommandError("Intent belongs to a different payment flow.")
        # With absent metadata require exact activation wording as an additional
        # provenance check; never infer ownership from the amount alone.
        if not metadata:
            description = str(stripe_value(pi, "description", "") or "")
            expected = f"{account.studio.name} family outstanding balance on AutoPay activation"
            if description != expected:
                raise CommandError("Unlabeled intent does not have expected activation description; manual review required.")
            if not profile.enabled_at or (stripe_value(pi, "created", 0) or 0) < int(profile.enabled_at.timestamp()):
                raise CommandError("Unlabeled payment predates family's AutoPay activation.")
        amount = Decimal(cents) / Decimal(100)
        existing = Payment.objects.filter(account=account, external_reference=pi_id).first()
        self.stdout.write(f"Stripe intent: {pi_id}; status: {status}; amount received: ${amount:.2f}; family account: {account.pk}; recorded: {bool(existing)}; account balance: ${account.balance:.2f}")
        if existing:
            self.stdout.write("Already recorded. Nothing to do.")
            return
        if not options["apply"]:
            self.stdout.write("DRY RUN. No database changes and no Stripe charge.")
            return
        with transaction.atomic():
            locked = FamilyAccount.objects.select_for_update().get(pk=account.pk)
            if locked.balance < amount:
                raise CommandError("Current balance is less than received payment; review the ledger before applying.")
            # Stripe metadata is absent on this verified historical intent.
            # Add *in-memory* verified attribution for the existing finalizer;
            # do not edit Stripe, create a PaymentIntent, or alter its status.
            # Build a plain dict from fields independently verified above.
            # StripeObject in installed stripe-python does not expose
            # to_dict_recursive(); its documented accessors vary by version.
            verified = {
                "id": stripe_value(pi, "id", ""),
                "status": status,
                "amount_received": cents,
                "currency": stripe_value(pi, "currency", ""),
                "customer": stripe_value(pi, "customer", ""),
                "payment_method": stripe_value(pi, "payment_method", ""),
            }
            verified["metadata"] = {
                "encore_kind": "family_balance_payment",
                "studio_id": str(account.studio_id),
                "family_account_id": str(account.pk),
                "family_id": str(account.family_id),
                "encore_reconciled": "verified_customer_and_method",
            }
            payment = finalize_family_balance_payment(verified, connected_account_id=connect_id)
            if payment is None:
                raise CommandError("Finalizer rejected payment; no ledger entry created.")
        account.refresh_from_db()
        self.stdout.write(self.style.SUCCESS(f"Recorded existing Stripe payment #{payment.pk} (${payment.amount:.2f}); remaining balance: ${account.balance:.2f}. No new debit initiated."))
