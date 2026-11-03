"""Reconcile refunds that Stripe has not yet reported as settled. Preview by default."""
from django.core.management.base import BaseCommand
from billing.models import PaymentRefund
from billing.refund_services import reconcile_refund
from billing.subscription_services import configure_stripe
import stripe


class Command(BaseCommand):
    help = "Preview pending refund statuses from Stripe; --apply updates the ledger after successful settlement."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        configure_stripe()
        for refund in PaymentRefund.objects.filter(status__in=["processing", "pending"]).order_by("pk"):
            if not refund.stripe_refund_id:
                self.stdout.write(self.style.WARNING(
                    f"Refund #{refund.pk}: no Stripe ID; investigate in Stripe using payment intent "
                    f"{refund.payment.external_reference} and idempotency key {refund.idempotency_key}. Do not submit again."))
                continue
            try:
                obj = stripe.Refund.retrieve(refund.stripe_refund_id, stripe_account=refund.stripe_account_id)
                self.stdout.write(f"Refund #{refund.pk}: Stripe reports {obj.status}")
                if options["apply"]:
                    reconcile_refund(refund.pk, obj, refund.stripe_account_id)
            except Exception as exc:
                self.stderr.write(f"Refund #{refund.pk} reconciliation failed: {exc}")
