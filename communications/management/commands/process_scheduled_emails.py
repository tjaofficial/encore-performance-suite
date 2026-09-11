from django.core.management.base import BaseCommand
from django.utils import timezone

from communications.models import EmailCampaign
from communications.services import send_campaign


class Command(BaseCommand):
    help = "Send Encore email campaigns whose scheduled time has arrived."

    def handle(self, *args, **options):
        campaigns = (
            EmailCampaign.objects
            .filter(
                status=EmailCampaign.Status.SCHEDULED,
                scheduled_for__isnull=False,
                scheduled_for__lte=timezone.now(),
            )
            .select_related(
                "studio",
                "signature",
            )
            .order_by(
                "scheduled_for",
            )
        )

        processed = 0

        for campaign in campaigns:
            result = send_campaign(
                campaign
            )

            processed += 1

            self.stdout.write(
                (
                    f"{campaign.name}: "
                    f"{result['sent']} sent, "
                    f"{result['failed']} failed, "
                    f"{result['suppressed']} suppressed"
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Processed {processed} scheduled campaign(s)."
            )
        )
