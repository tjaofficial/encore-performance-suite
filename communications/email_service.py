from dataclasses import dataclass
from typing import Iterable

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.utils.html import strip_tags
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)


class EncoreEmailError(Exception):
    pass


@dataclass(frozen=True)
class EmailSendResult:
    message_id: str
    response_metadata: dict


def _ses_client():
    kwargs = {
        "region_name": settings.AWS_SES_REGION,
    }

    if settings.AWS_ACCESS_KEY_ID:
        kwargs["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID

    if settings.AWS_SECRET_ACCESS_KEY:
        kwargs["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY

    if settings.AWS_SESSION_TOKEN:
        kwargs["aws_session_token"] = settings.AWS_SESSION_TOKEN

    return boto3.client(
        "sesv2",
        **kwargs,
    )


def _normalize_addresses(values: Iterable[str] | str | None):
    if not values:
        return []

    if isinstance(values, str):
        values = [values]

    return [
        value.strip()
        for value in values
        if value and value.strip()
    ]


def _ses_tags(tags):
    if not tags:
        return []

    if isinstance(tags, dict):
        tags = tags.items()

    return [
        {
            "Name": str(name),
            "Value": str(value),
        }
        for name, value in tags
        if name and value is not None
    ]


def send_email(
    *,
    to,
    subject,
    html_body,
    text_body=None,
    cc=None,
    bcc=None,
    reply_to=None,
    from_address=None,
    tags=None,
    configuration_set=None,
    sensitive=False,
):
    recipients = _normalize_addresses(to)

    if not recipients:
        raise EncoreEmailError(
            "At least one recipient is required."
        )

    cc_addresses = _normalize_addresses(cc)
    bcc_addresses = _normalize_addresses(bcc)

    # Respect studio Reply-To for every studio-tagged email, even if it did not
    # originate in send_studio_email(). Explicit reply_to retains precedence.
    studio_reply = None
    if not reply_to:
        try:
            from studios.models import Studio
            tag_pairs = dict(tags or {}) if not isinstance(tags, dict) else tags
            tag_id = str(tag_pairs.get("studio_id", ""))
            if tag_id.isdigit():
                studio_reply = Studio.objects.filter(pk=int(tag_id)).values_list("email", flat=True).first()
        except Exception:
            logger.exception("Studio reply-to lookup failed")
    reply_addresses = _normalize_addresses(
        reply_to or studio_reply or settings.EMAIL_REPLY_TO
    )

    sender = (
        from_address
        or settings.DEFAULT_FROM_EMAIL
    )

    if not text_body:
        text_body = strip_tags(html_body)

    request = {
        "FromEmailAddress": sender,
        "Destination": {
            "ToAddresses": recipients,
            "CcAddresses": cc_addresses,
            "BccAddresses": bcc_addresses,
        },
        "Content": {
            "Simple": {
                "Subject": {
                    "Data": subject,
                    "Charset": "UTF-8",
                },
                "Body": {
                    "Text": {
                        "Data": text_body,
                        "Charset": "UTF-8",
                    },
                    "Html": {
                        "Data": html_body,
                        "Charset": "UTF-8",
                    },
                },
            }
        },
    }

    if reply_addresses:
        request["ReplyToAddresses"] = reply_addresses

    selected_configuration_set = (
        configuration_set
        if configuration_set is not None
        else settings.SES_CONFIGURATION_SET
    )

    if selected_configuration_set:
        request["ConfigurationSetName"] = selected_configuration_set

    message_tags = _ses_tags(tags)

    if message_tags:
        request["EmailTags"] = message_tags

    # Central activity logging is intentionally a side effect of the shared SES send path.
    # Do not allow an audit DB issue to cause an extra financial/payment email retry.
    log_item = None
    try:
        from studios.models import Studio
        from .models import OutboundEmailLog
        tag_items = dict(tags or {}) if isinstance(tags, dict) else dict(tags or [])
        studio_id = str(tag_items.get("studio_id", "")).strip()
        studio = Studio.objects.filter(pk=int(studio_id)).first() if studio_id.isdigit() else None
        log_item = OutboundEmailLog.objects.create(
            studio=studio, to_addresses=recipients, cc_addresses=cc_addresses,
            bcc_addresses=bcc_addresses, sender=sender, reply_to_addresses=reply_addresses,
            subject=subject, text_body=("[Sensitive security content redacted]" if sensitive else text_body),
            html_body=("[Sensitive security content redacted]" if sensitive else html_body),
            category=str(tag_items.get("message_type", ""))[:80],
            source=str(tag_items.get("source", ""))[:80], status="sending",
        )
    except Exception:
        logger.exception("Unable to create outbound email activity record")

    try:
        response = _ses_client().send_email(
            **request
        )
    except (ClientError, BotoCoreError) as exc:
        if log_item:
            try:
                log_item.status = "failed"
                log_item.error = str(exc)[:3000]
                log_item.save(update_fields=["status", "error"])
            except Exception:
                logger.exception("Unable to save email send failure")
        raise EncoreEmailError(
            str(exc)
        ) from exc

    if log_item:
        try:
            log_item.status = "accepted"
            log_item.provider_message_id = response["MessageId"]
            log_item.accepted_at = timezone.now()
            log_item.save(update_fields=["status", "provider_message_id", "accepted_at"])
        except Exception:
            logger.exception("Unable to save SES acceptance event")
    return EmailSendResult(
        message_id=response["MessageId"],
        response_metadata=response.get(
            "ResponseMetadata",
            {},
        ),
    )


def send_test_email(recipient):
    return send_email(
        to=[recipient],
        subject="Encore SES Test",
        html_body="""
            <div style="font-family:Arial,sans-serif;">
                <h2>Encore Performance Suite</h2>
                <p>Amazon SES is connected successfully.</p>
                <p>
                    This message was sent from the local
                    Encore Django application.
                </p>
            </div>
        """,
        text_body=(
            "Encore Performance Suite\n\n"
            "Amazon SES is connected successfully.\n"
            "This message was sent from the local "
            "Encore Django application."
        ),
        tags={
            "message_type": "system_test",
            "source": "local_development",
        },
    )
