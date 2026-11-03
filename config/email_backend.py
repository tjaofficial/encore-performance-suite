from email.utils import getaddresses

import boto3
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend


class SESEmailBackend(BaseEmailBackend):
    """Django email backend that sends MIME messages through Amazon SES."""

    def _client(self):
        kwargs = {
            "region_name": getattr(settings, "AWS_SES_REGION", "us-east-2"),
        }

        access_key = getattr(settings, "AWS_ACCESS_KEY_ID", None)
        secret_key = getattr(settings, "AWS_SECRET_ACCESS_KEY", None)
        session_token = getattr(settings, "AWS_SESSION_TOKEN", None)

        if access_key and secret_key:
            kwargs["aws_access_key_id"] = access_key
            kwargs["aws_secret_access_key"] = secret_key
            if session_token:
                kwargs["aws_session_token"] = session_token

        return boto3.client("ses", **kwargs)

    def send_messages(self, email_messages):
        if not email_messages:
            return 0

        client = self._client()
        sent = 0

        for email_message in email_messages:
            try:
                mime_message = email_message.message()

                destinations = []
                for header_values in (
                    email_message.to,
                    email_message.cc,
                    email_message.bcc,
                ):
                    destinations.extend(
                        address
                        for _name, address in getaddresses(header_values or [])
                        if address
                    )

                params = {
                    "RawMessage": {
                        "Data": mime_message.as_bytes(),
                    },
                }

                if email_message.from_email:
                    params["Source"] = email_message.from_email

                if destinations:
                    params["Destinations"] = destinations

                configuration_set = getattr(
                    settings,
                    "SES_CONFIGURATION_SET",
                    "",
                )
                if configuration_set:
                    params["ConfigurationSetName"] = configuration_set

                client.send_raw_email(**params)
                sent += 1
            except Exception:
                if not self.fail_silently:
                    raise

        return sent
