
from django.core.management.base import BaseCommand

from billing.models import StudioSubscription
from billing.subscription_services import (
    evaluate_student_band_change,
)


class Command(BaseCommand):
    help = (
        "Review total student records and schedule "
        "Encore subscription band changes."
    )

    def handle(self, *args, **options):
        changed = 0

        subscriptions = (
            StudioSubscription.objects
            .filter(
                status__in=[
                    StudioSubscription.Status.ACTIVE,
                    StudioSubscription.Status.GRACE,
                    StudioSubscription.Status.CANCEL_AT_PERIOD_END,
                ]
            )
            .select_related(
                "studio",
            )
        )

        for subscription in subscriptions:
            if evaluate_student_band_change(
                subscription
            ):
                changed += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Scheduled {changed} student-band change(s)."
            )
        )
