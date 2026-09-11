from django.core.management.base import BaseCommand

from tasks.services import run_due_scheduled_templates


class Command(BaseCommand):
    help = (
        "Run due Encore Task Template date/time and recurring triggers."
    )

    def handle(
        self,
        *args,
        **options,
    ):
        runs = run_due_scheduled_templates()

        self.stdout.write(
            self.style.SUCCESS(
                f"Processed {len(runs)} task template run(s)."
            )
        )
