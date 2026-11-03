from django.contrib.auth import get_user_model

from studios.models import StudioMembership

from .models import (
    NotificationPreference,
    WorkspaceNotification,
)


User = get_user_model()


def notification_preference_for(user, studio):
    preference, _created = NotificationPreference.objects.get_or_create(
        user=user,
        studio=studio,
    )
    return preference


def notification_enabled(user, studio, field_name, default=True):
    if user is None or studio is None:
        return False

    preference = NotificationPreference.objects.filter(
        user=user,
        studio=studio,
    ).first()

    if preference is None:
        return default

    return bool(getattr(preference, field_name, default))


def create_workspace_notification(
    *,
    studio,
    user,
    category,
    kind,
    title,
    message="",
    action_url="",
    dedupe_key="",
    preference_field=None,
):
    if user is None:
        return None

    if (
        preference_field
        and not notification_enabled(
            user,
            studio,
            preference_field,
        )
    ):
        return None

    if (
        dedupe_key
        and WorkspaceNotification.objects.filter(
            studio=studio,
            user=user,
            dedupe_key=dedupe_key,
        ).exists()
    ):
        return None

    return WorkspaceNotification.objects.create(
        studio=studio,
        user=user,
        category=category,
        kind=kind,
        title=title,
        message=message,
        action_url=action_url,
        dedupe_key=dedupe_key,
    )


def administrator_users(studio):
    return User.objects.filter(
        studio_memberships__studio=studio,
        studio_memberships__role=StudioMembership.Role.ADMINISTRATOR,
        studio_memberships__is_active=True,
        is_active=True,
    ).distinct()


def guardian_users_for_student(student):
    """Active guardian accounts for the student's studio/family; distinct per user."""
    if not student.family_id:
        return []
    from families.models import Guardian
    return list(User.objects.filter(
        pk__in=Guardian.objects.filter(
            family_id=student.family_id, is_active=True, user__isnull=False,
        ).values_list("user_id", flat=True), is_active=True,
    ).distinct())


def notify_student_guardians(student, *, kind, title, message, action_url, event_key):
    """Exactly one notification per guardian and source event."""
    for guardian_user in guardian_users_for_student(student):
        create_workspace_notification(
            studio=student.studio, user=guardian_user,
            category=WorkspaceNotification.Category.TASK if kind.startswith("makeup_task") else WorkspaceNotification.Category.SYSTEM,
            kind=kind, title=title, message=message,
            action_url=action_url, dedupe_key=f"{event_key}:user:{guardian_user.pk}",
        )
