
from .models import (
    StudioSubscription,
    SubscriptionNotice,
)


def subscription_context(request):
    if not request.user.is_authenticated:
        return {}

    studio_slug = request.session.get(
        "encore_workspace_studio_slug"
    )

    role = request.session.get(
        "encore_workspace_role"
    )

    if (
        not studio_slug
        or role != "administrator"
    ):
        return {}

    subscription = (
        StudioSubscription.objects
        .filter(
            studio__slug=studio_slug,
        )
        .select_related(
            "studio",
        )
        .first()
    )

    if subscription is None:
        return {}

    latest_notice = (
        SubscriptionNotice.objects
        .filter(
            studio=subscription.studio,
            is_read=False,
        )
        .order_by(
            "-created_at",
        )
        .first()
    )

    return {
        "encore_subscription": subscription,
        "encore_subscription_notice": latest_notice,
    }
