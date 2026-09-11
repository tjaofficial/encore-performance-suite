from django import template

from accounts.dashboard_quick_actions import (
    normalize_class_quick_actions,
)
from accounts.models import DashboardPreference

register = template.Library()


@register.simple_tag
def class_quick_action_enabled(
    user,
    studio,
    action_key,
):
    if (
        not user
        or not getattr(
            user,
            "is_authenticated",
            False,
        )
        or studio is None
    ):
        return True

    preference = (
        DashboardPreference.objects
        .filter(
            user=user,
            studio=studio,
            dashboard_type=(
                DashboardPreference
                .DashboardType
                .CLASS
            ),
        )
        .first()
    )

    raw_actions = {}

    if (
        preference
        and isinstance(
            preference.layout,
            dict,
        )
    ):
        raw_actions = (
            preference.layout.get(
                "quick_actions",
                {},
            )
        )

    normalized = normalize_class_quick_actions(
        raw_actions
    )

    return normalized.get(
        action_key,
        True,
    )
