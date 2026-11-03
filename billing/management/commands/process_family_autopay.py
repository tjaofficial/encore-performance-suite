from django.core.management.base import BaseCommand
from billing.autopay_services import collect_due_autopay, send_autopay_reminders, reconcile_pending_autopay


class Command(BaseCommand):
    help = 'Process consented family tuition AutoPay and monthly opt-in reminders. Preview by default.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Actually charge and notify. Use only on scheduled production worker.')

    def handle(self, *args, **opts):
        dry_run = not opts['apply']
        self.stdout.write(f"Pending ACH reconciliation: {reconcile_pending_autopay(dry_run=dry_run)}")
        self.stdout.write(f'AutoPay {"PREVIEW" if dry_run else "APPLY"}: {collect_due_autopay(dry_run=dry_run)}')
        self.stdout.write(f'Reminders: {send_autopay_reminders(dry_run=dry_run)}')
