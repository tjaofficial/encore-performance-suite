"""Inspect or explicitly retry a previously authorized activation balance in TEST mode.

Dry-run by default. Does not silently collect when a user loads a page.
"""
from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from billing.models import FamilyAccount, FamilyAutoPayProfile
from billing.stripe_environment import stripe_mode, connected_account_for_subscription
from billing.parent_payment_services import pending_family_intents, FAMILY_BALANCE_PAYMENT_KIND
from billing.subscription_services import configure_stripe, stripe_metadata, stripe_value
import stripe
from billing.autopay_services import collect_activation_balance_once

class Command(BaseCommand):
    help = "Inspect family AutoPay activation payment; explicit sandbox-only recovery."

    def add_arguments(self, parser):
        parser.add_argument("account_id", type=int)
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--authorize-amount", type=str, default="")

    def handle(self, *args, **opts):
        account = FamilyAccount.objects.select_related("studio").filter(pk=opts["account_id"]).first()
        if not account:
            raise CommandError("Family account not found.")
        subscription = getattr(account.studio, "subscription", None)
        if not subscription:
            raise CommandError("Studio has no subscription/Connect configuration.")
        profile = FamilyAutoPayProfile.objects.filter(account=account, mode=stripe_mode()).first()
        if not profile or not profile.is_enabled:
            raise CommandError("AutoPay is not enabled for this family.")
        if profile.connected_account_id != connected_account_for_subscription(subscription):
            raise CommandError("Wrong connected account.")
        pending = pending_family_intents(account, profile.connected_account_id, profile.stripe_customer_id)
        self.stdout.write(f"Stripe mode: {profile.mode}; balance: {account.balance}; saved method: {profile.payment_method_type}; pending payment attempts: {len(pending)}")
        for intent in pending:
            self.stdout.write(f"  {intent.id}: {intent.status}")
        if not opts["apply"]:
            self.stdout.write("DRY RUN. No payment was initiated.")
            return
        if profile.mode != "test":
            raise CommandError("This recovery command is sandbox-only.")
        if pending:
            raise CommandError("An existing payment is processing. No new debit initiated.")
        # A recently succeeded payment may have missed its webhook and still
        # be absent from the local ledger. Never charge that amount a second time.
        configure_stripe()
        intents = stripe.PaymentIntent.list(
            customer=profile.stripe_customer_id, limit=100,
            stripe_account=profile.connected_account_id,
        )
        for intent in stripe_value(intents, "data", []) or []:
            metadata = stripe_metadata(intent)
            if (metadata.get("encore_kind") == FAMILY_BALANCE_PAYMENT_KIND
                    and str(metadata.get("family_account_id")) == str(account.pk)
                    and stripe_value(intent, "status") == "succeeded"
                    and stripe_value(intent, "created", 0) >= int(profile.enabled_at.timestamp())
                    and stripe_value(intent, "amount_received", 0) == int(account.balance * 100)):
                raise CommandError(
                    f"Stripe has a succeeded family payment {intent.id} since activation. "
                    "Reconcile that payment before any recovery debit."
                )
        if not opts["authorize_amount"]:
            raise CommandError("--apply requires --authorize-amount equal to the original amount the family approved.")
        try:
            cap = Decimal(opts["authorize_amount"])
        except Exception as exc:
            raise CommandError("Invalid authorized amount.") from exc
        if cap <= 0 or cap != account.balance:
            raise CommandError("Balance differs from authorized amount. Re-authorize with the parent before collecting.")
        profile._activation_balance_authorized = cap
        try:
            result = collect_activation_balance_once(account, subscription, profile, recovery=True)
        except stripe.error.StripeError as exc:
            raise CommandError(f"Stripe rejected the recovery debit: {exc}") from exc
        self.stdout.write(str(result))
