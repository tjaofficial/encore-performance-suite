import uuid
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape

from communications.email_service import EncoreEmailError, send_email


class InstructorActivationError(Exception):
    pass


def _absolute_url(request, path):
    base = str(getattr(settings, "ENCORE_BASE_URL", "") or "").strip().rstrip("/")
    if base:
        return f"{base}{path}"
    return request.build_absolute_uri(path)


def send_instructor_activation(*, request, instructor):
    email = str(instructor.email or "").strip()
    try:
        validate_email(email)
    except ValidationError as exc:
        raise InstructorActivationError("A valid instructor email address is required.") from exc

    instructor.activation_token = uuid.uuid4()
    instructor.activation_sent_at = timezone.now()
    instructor.activation_expires_at = timezone.now() + timedelta(days=7)
    instructor.is_active = True
    instructor.save(
        update_fields=[
            "activation_token",
            "activation_sent_at",
            "activation_expires_at",
            "is_active",
            "updated_at",
        ]
    )

    claim_path = reverse(
        "instructors:instructor_claim_profile",
        kwargs={"activation_token": instructor.activation_token},
    )
    claim_url = _absolute_url(request, claim_path)

    first_name = instructor.first_name or "Instructor"
    studio_name = instructor.studio.name
    html_body = f"""
        <div style="font-family:Arial,sans-serif;line-height:1.6;color:#10153f;max-width:640px;margin:0 auto;">
            <h2 style="margin-bottom:8px;">Welcome to Encore Performance Suite</h2>
            <p>Hello {escape(first_name)},</p>
            <p><strong>{escape(studio_name)}</strong> has invited you to activate your Encore instructor account.</p>
            <p>Use the secure link below to verify your instructor profile, create or connect your Encore login, and confirm your weekly teaching availability.</p>
            <p style="margin:24px 0;">
                <a href="{escape(claim_url)}" style="display:inline-block;padding:12px 18px;border-radius:9px;background:#265dff;color:#fff;text-decoration:none;font-weight:700;">
                    Activate My Encore Account
                </a>
            </p>
            <p style="font-size:13px;color:#667085;">This activation link expires in 7 days. If you were not expecting this invitation, you can ignore this email.</p>
        </div>
    """
    text_body = (
        f"Hello {first_name},\n\n"
        f"{studio_name} has invited you to activate your Encore instructor account.\n\n"
        "Use the secure link below to verify your profile, create or connect your login, "
        "and confirm your weekly teaching availability.\n\n"
        f"Activate your account: {claim_url}\n\n"
        "This activation link expires in 7 days."
    )

    try:
        send_email(
            to=[email],
            subject=f"Activate your {studio_name} Encore instructor account",
            html_body=html_body,
            text_body=text_body,
            tags={
                "message_type": "instructor_activation",
                "studio_id": instructor.studio_id,
            },
            sensitive=True,
        )
    except EncoreEmailError as exc:
        instructor.activation_sent_at = None
        instructor.activation_expires_at = None
        instructor.save(
            update_fields=[
                "activation_sent_at",
                "activation_expires_at",
                "updated_at",
            ]
        )
        raise InstructorActivationError(str(exc)) from exc

    return claim_url
