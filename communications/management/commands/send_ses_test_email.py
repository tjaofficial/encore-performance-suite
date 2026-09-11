from django.core.management.base import BaseCommand, CommandError

from communications.email_service import (
    EncoreEmailError,
    send_test_email,
)


class Command(BaseCommand):
    help = "Send a real test email through Amazon SES."

    def add_arguments(self, parser):
        parser.add_argument(
            "recipient",
            help=(
                "Recipient email address. While SES is in sandbox, "
                "use a verified recipient or the SES mailbox simulator."
            ),
        )

    def handle(self, *args, **options):
        recipient = options["recipient"]

        self.stdout.write(
            f"Sending SES test email to {recipient}..."
        )

        try:
            result = send_test_email(recipient)
        except EncoreEmailError as exc:
            raise CommandError(
                f"SES send failed: {exc}"
            ) from exc

        self.stdout.write(
            self.style.SUCCESS(
                "SES accepted the email. "
                f"Message ID: {result.message_id}"
            )
        )
