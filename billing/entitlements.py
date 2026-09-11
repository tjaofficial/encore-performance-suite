
ESSENTIALS_FEATURES = {
    "students",
    "families",
    "instructors",
    "classes",
    "seasons",
    "enrollment",
    "waitlists",
    "scheduling",
    "attendance",
    "calendar_basic",
    "tasks_basic",
    "announcements",
    "notifications",
    "family_portal",
    "teacher_portal",
    "student_portal",
    "email_basic",
    "registration",
    "reports_basic",
    "studio_branding",
}

PRO_FEATURES = ESSENTIALS_FEATURES | {
    "evaluations",
    "task_templates",
    "task_automation",
    "calendar_advanced",
    "teacher_time_off",
    "substitute_management",
    "email_templates",
    "email_signatures",
    "email_campaigns",
    "email_scheduling",
    "email_analytics",
    "email_automation",
    "birthday_email",
    "costumes",
    "measurements",
    "music_management",
    "dance_management",
    "dashboard_customization",
    "reports_advanced",
    "multi_location",
}


def subscription_features(subscription):
    if subscription.plan_tier == "pro":
        features = set(PRO_FEATURES)
    else:
        features = set(ESSENTIALS_FEATURES)

    if subscription.drawing_board_enabled:
        features.add(
            "drawing_board"
        )

    return features


def has_subscription_feature(
    subscription,
    feature,
):
    return feature in subscription_features(
        subscription
    )
