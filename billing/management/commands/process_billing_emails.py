from django.core.management.base import BaseCommand
from billing.email_notifications import queue_upcoming_tuition, dispatch_billing_emails
from billing.models import BillingEmailDelivery

class Command(BaseCommand):
    help='Preview or process family billing emails. Sending requires --apply.'
    def add_arguments(self, parser):
        parser.add_argument('--apply',action='store_true')
        parser.add_argument('--retry-failed',action='store_true')
        parser.add_argument('--limit',type=int,default=100)
        parser.add_argument('--days-ahead',type=int,default=5)
    def handle(self,*args,**options):
        if not 0 <= options['days_ahead'] <= 30:
            self.stderr.write('days-ahead must be between 0 and 30');return
        upcoming=queue_upcoming_tuition(days_ahead=options['days_ahead'],dry_run=not options['apply'])
        self.stdout.write(f'Upcoming tuition: {upcoming}')
        if not options['apply']:
            self.stdout.write(f"Pending: {BillingEmailDelivery.objects.filter(status='pending').count()}; failed: {BillingEmailDelivery.objects.filter(status='failed').count()}")
            self.stdout.write('DRY RUN. No email sent.');return
        self.stdout.write(str(dispatch_billing_emails(limit=max(1,min(options['limit'],500)), retry_failed=options['retry_failed'])))
