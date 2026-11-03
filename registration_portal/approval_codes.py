"""Class registration approval codes; never retain plaintext codes."""
import hashlib
import hmac
import secrets
from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from .models import ClassApprovalCode


def _digest(code):
    normalized = "".join(char for char in str(code).upper() if char.isalnum())
    return hmac.new(settings.SECRET_KEY.encode(), normalized.encode(), hashlib.sha256).hexdigest()


def issue(studio, class_instance, email, admin, *, days=7):
    if class_instance.studio_id != studio.id or class_instance.registration_mode != 'approval':
        raise ValueError('Choose an approval-required class from this studio.')
    code = '-'.join(''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(4)) for _ in range(3))
    row = ClassApprovalCode.objects.create(studio=studio, class_instance=class_instance,
        parent_email=email.strip().lower(), code_hash=_digest(code),
        expires_at=timezone.now()+timedelta(days=days), issued_by=admin)
    return row, code


@transaction.atomic
def claim(session, student_key, class_instance, code):
    entry = (ClassApprovalCode.objects.select_for_update().filter(
        studio=session.studio, class_instance=class_instance, code_hash=_digest(code),
        parent_email=(session.contact_email or '').strip().lower(),
        expires_at__gt=timezone.now(), revoked_at__isnull=True, used_at__isnull=True
    ).first())
    if entry is None or (entry.claimed_session_id and entry.claimed_session_id != session.pk) or (
        entry.claimed_student_key and entry.claimed_student_key != student_key
    ):
        return None
    entry.claimed_session = session
    entry.claimed_student_key = student_key
    entry.save(update_fields=['claimed_session','claimed_student_key'])
    return entry.pk


def validate_session(session):
    """Require still-valid approval for every dancer/class, including after wizard edits."""
    data = session.student_data or {}
    assignments = data.get('assignments') or {}
    grants = data.get('approval_grants') or {}
    from classes.models import Class
    class_ids = {int(pk) for ids in assignments.values() for pk in ids if str(pk).isdigit()}
    restricted = Class.objects.filter(studio=session.studio, pk__in=class_ids, registration_mode='approval')
    now = timezone.now()
    for klass in restricted:
        for student_key, ids in assignments.items():
            if klass.pk not in [int(pk) for pk in ids if str(pk).isdigit()]:
                continue
            grant_id = (grants.get(student_key) or {}).get(str(klass.pk))
            if not grant_id or not ClassApprovalCode.objects.filter(
                pk=grant_id, studio=session.studio, class_instance=klass,
                claimed_session=session, claimed_student_key=student_key,
                parent_email=(session.contact_email or '').strip().lower(),
                expires_at__gt=now, revoked_at__isnull=True, used_at__isnull=True
            ).exists():
                raise ValueError(f'An active in-person approval code is required for {klass.name}. Return to class selection.')


def consume_session(session):
    data = session.student_data or {}
    grants = data.get('approval_grants') or {}
    assignments = data.get('assignments') or {}
    ids = [pk for student_key, values in grants.items()
           for class_id, pk in values.items()
           if int(class_id) in [int(cid) for cid in assignments.get(student_key, [])]]
    ClassApprovalCode.objects.filter(pk__in=ids, claimed_session=session, used_at__isnull=True).update(used_at=timezone.now())


def code_is_eligible(session, student_key, class_instance, code):
    """Read-only eligibility check for class picker; final wizard submission claims the code."""
    if not code or class_instance.studio_id != session.studio_id or class_instance.registration_mode != "approval":
        return False
    entry = ClassApprovalCode.objects.filter(
        studio=session.studio, class_instance=class_instance, code_hash=_digest(code),
        parent_email=(session.contact_email or "").strip().lower(),
        expires_at__gt=timezone.now(), revoked_at__isnull=True, used_at__isnull=True,
    ).first()
    return bool(entry and (not entry.claimed_session_id or entry.claimed_session_id == session.pk)
                and (not entry.claimed_student_key or entry.claimed_student_key == student_key))
