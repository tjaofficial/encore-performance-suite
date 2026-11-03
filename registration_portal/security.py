import secrets
from datetime import timedelta
from urllib import parse

from django.conf import settings
from django.core import signing
from django.core.mail import send_mail
from django.urls import reverse
from django.utils import timezone

from .models import PublicRegistrationSession


SECURITY_KEY = "_registration_security"
VERIFICATION_SALT = "encore.public-registration.email-verification.v1"


def client_ip(request):
    forwarded = (request.META.get("HTTP_X_FORWARDED_FOR") or "").strip()
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return (request.META.get("REMOTE_ADDR") or "").strip()


def registration_security_state(registration_session):
    data = registration_session.account_data or {}
    state = data.get(SECURITY_KEY) or {}
    return dict(state) if isinstance(state, dict) else {}


def _save_security_state(registration_session, state):
    data = dict(registration_session.account_data or {})
    data[SECURITY_KEY] = dict(state)
    registration_session.account_data = data
    registration_session.save(update_fields=["account_data", "updated_at"])


def seed_registration_security(registration_session, request):
    state = registration_security_state(registration_session)
    state.setdefault("source_ip", client_ip(request))
    state.setdefault("started_at", timezone.now().isoformat())
    _save_security_state(registration_session, state)


def security_state_for_account_update(registration_session, request):
    previous = registration_security_state(registration_session)
    return {
        "source_ip": previous.get("source_ip") or client_ip(request),
        "started_at": previous.get("started_at") or timezone.now().isoformat(),
    }


def mark_existing_account_trusted(registration_session, request):
    state = security_state_for_account_update(registration_session, request)
    state.update(
        {
            "trusted_existing_account": True,
            "authenticated_at": timezone.now().isoformat(),
        }
    )
    return state


def registration_uses_existing_account(registration_session):
    data = registration_session.account_data or {}
    return bool(
        data.get("account_mode") == "existing"
        and data.get("existing_user_id")
    )


def registration_identity_verified(registration_session):
    if registration_uses_existing_account(registration_session):
        return True

    state = registration_security_state(registration_session)
    verified_at = state.get("email_verified_at")
    verified_email = (state.get("verified_email") or "").strip().lower()
    current_email = (registration_session.contact_email or "").strip().lower()
    return bool(verified_at and current_email and verified_email == current_email)



def registration_start_allowed(ip_address):
    if not ip_address:
        return True
    cutoff = timezone.now() - timedelta(hours=1)
    limit = int(getattr(settings, "REGISTRATION_START_LIMIT_PER_HOUR", 20))
    recent_sessions = PublicRegistrationSession.objects.filter(
        created_at__gte=cutoff,
    ).values_list("account_data", flat=True)
    count = 0
    for data in recent_sessions:
        if not isinstance(data, dict):
            continue
        state = data.get(SECURITY_KEY) or {}
        if isinstance(state, dict) and state.get("source_ip") == ip_address:
            count += 1
            if count >= limit:
                return False
    return True


def email_session_allowed(email):
    email = (email or "").strip().lower()
    if not email:
        return False
    cutoff = timezone.now() - timedelta(hours=1)
    limit = int(getattr(settings, "REGISTRATION_EMAIL_SESSION_LIMIT_PER_HOUR", 5))
    count = PublicRegistrationSession.objects.filter(
        created_at__gte=cutoff,
        contact_email__iexact=email,
    ).count()
    return count <= limit


def _recent_timestamps(values, *, minutes):
    cutoff = timezone.now() - timedelta(minutes=minutes)
    kept = []
    for raw in values or []:
        try:
            value = timezone.datetime.fromisoformat(raw)
            if timezone.is_naive(value):
                value = timezone.make_aware(value, timezone.get_current_timezone())
        except (TypeError, ValueError):
            continue
        if value >= cutoff:
            kept.append(value)
    return kept


def verification_send_allowed(registration_session):
    state = registration_security_state(registration_session)
    recent = _recent_timestamps(
        state.get("verification_send_history"),
        minutes=60,
    )
    limit = int(getattr(settings, "REGISTRATION_VERIFICATION_EMAIL_LIMIT_PER_HOUR", 4))
    return len(recent) < limit



def _verification_token(registration_session, nonce):
    return signing.dumps(
        {
            "registration_token": str(registration_session.token),
            "email": (registration_session.contact_email or "").strip().lower(),
            "nonce": nonce,
        },
        salt=VERIFICATION_SALT,
        compress=True,
    )


def send_registration_verification_email(request, registration_session):
    if registration_uses_existing_account(registration_session):
        return

    if not email_session_allowed(registration_session.contact_email):
        raise ValueError(
            "Too many registration attempts were started for this email. Please wait before trying again."
        )

    if not verification_send_allowed(registration_session):
        raise ValueError(
            "Too many verification emails were requested. Please wait before requesting another."
        )

    state = registration_security_state(registration_session)
    nonce = secrets.token_urlsafe(24)
    now = timezone.now()
    recent = _recent_timestamps(
        state.get("verification_send_history"),
        minutes=60,
    )
    recent.append(now)
    state.update(
        {
            "verification_nonce": nonce,
            "verification_sent_at": now.isoformat(),
            "verification_send_history": [value.isoformat() for value in recent],
            "verified_email": "",
            "email_verified_at": "",
        }
    )
    _save_security_state(registration_session, state)

    token = _verification_token(registration_session, nonce)
    verification_path = reverse(
        "registration_portal:registration_verify_email",
        kwargs={
            "studio_slug": registration_session.studio.slug,
            "token": registration_session.token,
        },
    )
    base_url = f"{settings.ENCORE_BASE_URL}{verification_path}"
    verify_url = f"{base_url}?{parse.urlencode({'code': token})}"

    subject = f"Verify your email for {registration_session.studio.name} registration"
    body = (
        f"You're almost finished registering with {registration_session.studio.name}.\n\n"
        "Open the secure link below, then confirm your email to continue to checkout.\n\n"
        f"{verify_url}\n\n"
        "This verification link expires in 60 minutes. If you did not start this registration, you can ignore this email."
    )

    from communications.studio_email import send_studio_email
    from django.utils.html import escape
    send_studio_email(
        studio=registration_session.studio, to=[registration_session.contact_email],
        subject=subject,
        html_body=f'<div style="white-space:pre-line">{escape(body)}</div>',
        text_body=body, sensitive=True,
        tags={'message_type':'registration_verification'},
    )


def validate_registration_verification_code(registration_session, code):
    try:
        payload = signing.loads(
            code,
            salt=VERIFICATION_SALT,
            max_age=int(getattr(settings, "REGISTRATION_EMAIL_VERIFICATION_MAX_AGE_SECONDS", 3600)),
        )
    except signing.SignatureExpired:
        return False, "That verification link has expired. Request a new email and try again."
    except signing.BadSignature:
        return False, "That verification link is invalid. Request a new email and try again."

    state = registration_security_state(registration_session)
    expected_email = (registration_session.contact_email or "").strip().lower()
    if (
        payload.get("registration_token") != str(registration_session.token)
        or payload.get("email") != expected_email
        or payload.get("nonce") != state.get("verification_nonce")
    ):
        return False, "That verification link is no longer valid. Request a new email and try again."

    return True, ""


def mark_registration_email_verified(registration_session):
    state = registration_security_state(registration_session)
    state.update(
        {
            "email_verified_at": timezone.now().isoformat(),
            "verified_email": (registration_session.contact_email or "").strip().lower(),
            "verification_nonce": "",
        }
    )
    _save_security_state(registration_session, state)
