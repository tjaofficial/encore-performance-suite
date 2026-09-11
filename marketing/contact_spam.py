import hashlib
import re
import time
from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache
from django.core import signing


URL_RE = re.compile(
    r"(?:https?://|www\.)",
    re.IGNORECASE,
)

SUSPICIOUS_PATTERNS = [
    re.compile(r"\bseo\b", re.IGNORECASE),
    re.compile(r"\bbacklinks?\b", re.IGNORECASE),
    re.compile(r"\bguest posts?\b", re.IGNORECASE),
    re.compile(r"\bcrypto(?:currency)?\b", re.IGNORECASE),
    re.compile(r"\bbitcoin\b", re.IGNORECASE),
    re.compile(r"\bcasino\b", re.IGNORECASE),
    re.compile(r"\bviagra\b", re.IGNORECASE),
    re.compile(r"\bweb traffic\b", re.IGNORECASE),
    re.compile(r"\blead generation\b", re.IGNORECASE),
    re.compile(r"\bmarketing services?\b", re.IGNORECASE),
    re.compile(r"\bgoogle ranking\b", re.IGNORECASE),
    re.compile(r"\bsearch engine optimization\b", re.IGNORECASE),
]

MIN_FORM_SECONDS = 3
MAX_FORM_AGE_SECONDS = 60 * 60 * 6
MAX_URLS = 3
RATE_LIMIT_WINDOW_SECONDS = 60 * 60
RATE_LIMIT_MAX = 5


@dataclass(frozen=True)
class ContactSpamResult:
    is_spam: bool
    reason: str = ""


def create_contact_form_token():
    return signing.dumps(
        {
            "loaded_at": time.time(),
        },
        salt="encore-public-contact",
        compress=True,
    )


def _token_age_seconds(token):
    if not token:
        return None

    try:
        payload = signing.loads(
            token,
            salt="encore-public-contact",
            max_age=MAX_FORM_AGE_SECONDS,
        )
    except signing.BadSignature:
        return None
    except signing.SignatureExpired:
        return None

    loaded_at = payload.get("loaded_at")

    if not isinstance(
        loaded_at,
        (
            int,
            float,
        ),
    ):
        return None

    return max(
        0,
        time.time() - loaded_at,
    )


def _client_ip(request):
    forwarded = request.META.get(
        "HTTP_X_FORWARDED_FOR",
        "",
    )

    if forwarded:
        return forwarded.split(",")[0].strip()

    return request.META.get(
        "REMOTE_ADDR",
        "",
    ).strip()


def _rate_limit_key(request):
    raw = (
        _client_ip(request)
        or request.session.session_key
        or "unknown"
    )

    digest = hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()

    return f"encore-contact-rate:{digest}"


def _rate_limited(request):
    key = _rate_limit_key(request)

    try:
        current = cache.get(key, 0)

        if current >= RATE_LIMIT_MAX:
            return True

        if current == 0:
            cache.set(
                key,
                1,
                RATE_LIMIT_WINDOW_SECONDS,
            )
        else:
            try:
                cache.incr(key)
            except ValueError:
                cache.set(
                    key,
                    current + 1,
                    RATE_LIMIT_WINDOW_SECONDS,
                )
    except Exception:
        # Contact form should still work if cache is unavailable.
        return False

    return False


def classify_contact_submission(
    request,
    *,
    cleaned_data,
    form_token,
):
    if cleaned_data.get("website"):
        return ContactSpamResult(
            True,
            "honeypot",
        )

    age = _token_age_seconds(form_token)

    if age is None:
        return ContactSpamResult(
            True,
            "invalid_form_token",
        )

    if age < MIN_FORM_SECONDS:
        return ContactSpamResult(
            True,
            "submitted_too_fast",
        )

    if _rate_limited(request):
        return ContactSpamResult(
            True,
            "rate_limit",
        )

    message = cleaned_data.get(
        "message",
        "",
    )

    name = cleaned_data.get(
        "name",
        "",
    )

    studio_name = cleaned_data.get(
        "studio_name",
        "",
    )

    combined = " ".join(
        [
            name,
            studio_name,
            message,
        ]
    ).strip()

    url_count = len(
        URL_RE.findall(combined)
    )

    if url_count > MAX_URLS:
        return ContactSpamResult(
            True,
            "too_many_links",
        )

    suspicious_hits = sum(
        1
        for pattern in SUSPICIOUS_PATTERNS
        if pattern.search(combined)
    )

    if suspicious_hits >= 2:
        return ContactSpamResult(
            True,
            "spam_content",
        )

    if len(set(message.lower().split())) <= 3 and len(message) > 80:
        return ContactSpamResult(
            True,
            "repetitive_content",
        )

    return ContactSpamResult(False)
