from django.core.management.base import BaseCommand
from billing.autopay_services import reconcile_pending_autopay, collect_due_autopay, send_autopay_reminders
from billing.overdue_services import process_overdue
from billing.services import generate_due_recurring_charges
from billing.models import RecurringChargeSchedule
from django.utils import timezone

class Command(BaseCommand):
    help = "Daily, idempotent tuition workflow. Preview by default. Schedule --apply once daily."
    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--skip-reminders", action="store_true")
    def handle(self, *args, **options):
        dry_run = not options["apply"]
        self.stdout.write("PREVIEW" if dry_run else "APPLY")
        if dry_run:
            count = RecurringChargeSchedule.objects.filter(is_active=True, next_charge_date__lte=timezone.localdate()).count()
            self.stdout.write(f"Recurring schedules due (preview only): {count}")
        else:
            # Generate charges before attempting collection. The generator
            # deduplicates by recurring schedule + due date.
            self.stdout.write(f"Recurring charges: {generate_due_recurring_charges()}")
        reconciled = reconcile_pending_autopay(dry_run=dry_run)
        self.stdout.write(f"Stripe ACH reconciliation: {reconciled}")
        # Abort when any Stripe retrieval failed: don't send potentially false expiry notices.
        if reconciled.get("errors"):
            self.stderr.write("Stripe reconciliation errors detected. Skipping downstream work.")
            return
        self.stdout.write(f"Consented unpaid AutoPay: {collect_due_autopay(dry_run=dry_run)}")
        if not options["skip_reminders"]:
            self.stdout.write(f"AutoPay opt-in reminders: {send_autopay_reminders(dry_run=dry_run)}")
        self.stdout.write(f"Overdue notices and human-review flags: {process_overdue(dry_run=dry_run)}")
        self.stdout.write("No automatic enrollment removals or automatic repeat payment attempts.")
