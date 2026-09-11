
from django.core.management.base import BaseCommand
from django.utils import timezone

from billing.models import StudioSubscription


class Command(BaseCommand):
    help = (
        "Restrict studios whose Encore subscription "
        "grace period has expired."
    )

    def handle(self, *args, **options):
        now = timezone.now()
        restricted = 0

        subscriptions = (
            StudioSubscription.objects
            .filter(
                status=StudioSubscription.Status.GRACE,
                grace_period_ends_at__isnull=False,
                grace_period_ends_at__lte=now,
                studio__is_active=True,
            )
            .select_related(
                "studio",
            )
        )

        for subscription in subscriptions:
            subscription.status = (
                StudioSubscription.Status.PAST_DUE
            )

            subscription.save(
                update_fields=[
                    "status",
                    "updated_at",
                ]
            )

            subscription.studio.is_active = False

            subscription.studio.save(
                update_fields=[
                    "is_active",
                    "updated_at",
                ]
            )

            restricted += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Restricted {restricted} studio(s)."
            )
        )
