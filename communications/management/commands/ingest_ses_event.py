import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from communications.services import record_ses_event


class Command(BaseCommand):
    help = "Ingest one saved Amazon SES/EventBridge event JSON file."

    def add_arguments(self, parser):
        parser.add_argument(
            "json_file",
            help="Path to an SES/EventBridge event JSON file.",
        )

    def handle(self, *args, **options):
        path = Path(
            options["json_file"]
        )

        if not path.exists():
            raise CommandError(
                f"File not found: {path}"
            )

        payload = json.loads(
            path.read_text()
        )

        recipient = record_ses_event(
            payload
        )

        if recipient is None:
            raise CommandError(
                "No Encore recipient matched the SES message ID."
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Recorded SES event for {recipient.email}."
            )
        )
