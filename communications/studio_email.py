"""Send family-facing studio-branded mail through Encore's verified SES identity.

Use this for future parent invoices, tuition notices and receipts. It deliberately
keeps the authenticated From address on Encore's verified sending domain; the
studio's published email is used only as Reply-To. No per-studio SES setup needed.
"""
from email.utils import formataddr

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from .email_service import send_email


def send_studio_email(*, studio, to, subject, html_body, text_body=None,
                      cc=None, bcc=None, tags=None, sensitive=False):
    studio_name = str(getattr(studio, "name", "") or "Dance Studio").replace("\r", " ").replace("\n", " ").strip()
    verified_sender = str(getattr(settings, "EMAIL_FROM_ADDRESS", "") or "").strip()
    validate_email(verified_sender)
    reply_address = str(getattr(studio, "email", "") or "").strip()
    if reply_address:
        try:
            validate_email(reply_address)
        except ValidationError:
            reply_address = ""
    return send_email(
        to=to,
        subject=subject,
        html_body=html_body,
        text_body=text_body,
        cc=cc,
        bcc=bcc,
        from_address=formataddr((studio_name, verified_sender)),
        reply_to=reply_address or getattr(settings, "EMAIL_REPLY_TO", verified_sender),
        sensitive=sensitive,
        tags={**(tags or {}), "studio_id": str(studio.pk), "source": "studio_branded"},
    )
