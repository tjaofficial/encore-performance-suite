from django import template
from django.urls import (
    NoReverseMatch,
    reverse,
)

from accounts.dashboard_quick_links import (
    normalize_dashboard_quick_links,
    quick_link_definitions,
)
from accounts.models import DashboardPreference


register = template.Library()


DASHBOARD_TYPE_MAP = {
    "admin": DashboardPreference.DashboardType.ADMIN,
    "teacher": DashboardPreference.DashboardType.TEACHER,
    "class": DashboardPreference.DashboardType.CLASS,
}


def _safe_reverse(
    name,
    *,
    kwargs=None,
):
    try:
        return reverse(
            name,
            kwargs=kwargs or {},
        )
    except NoReverseMatch:
        return ""


def _builtin_url(
    key,
    *,
    dashboard_kind,
    studio,
    class_instance=None,
    performance_plan=None,
):
    studio_kwargs = {
        "studio_slug": studio.slug,
    }

    if dashboard_kind == "admin":
        mapping = {
            "calendar": (
                "scheduling:calendar",
                studio_kwargs,
            ),
            "classes": (
                "classes:class_list",
                studio_kwargs,
            ),
            "students": (
                "students:student_list",
                studio_kwargs,
            ),
            "instructors": (
                "instructors:instructor_list",
                studio_kwargs,
            ),
            "announcements": (
                "communications:announcement_list",
                studio_kwargs,
            ),
            "tasks": (
                "tasks:task_list",
                studio_kwargs,
            ),
        }

    elif dashboard_kind == "teacher":
        mapping = {
            "calendar": (
                "scheduling:calendar",
                studio_kwargs,
            ),
            "add_reminder": (
                "tasks:task_create",
                studio_kwargs,
            ),
            "log_extra_work": (
                "timekeeping:extra_work_create",
                studio_kwargs,
            ),
            "announcements": (
                "communications:announcement_list",
                studio_kwargs,
            ),
        }

    else:
        class_kwargs = {
            **studio_kwargs,
            "class_id": (
                class_instance.id
                if class_instance is not None
                else 0
            ),
        }

        if (
            key == "performance"
            and performance_plan is not None
        ):
            return _safe_reverse(
                "performance:plan_detail",
                kwargs={
                    **studio_kwargs,
                    "plan_id": performance_plan.id,
                },
            )

        mapping = {
            "attendance": (
                "attendance:take_attendance",
                class_kwargs,
            ),
            "music": (
                "resources:resource_list",
                studio_kwargs,
            ),
            "videos": (
                "resources:resource_list",
                studio_kwargs,
            ),
            "performance": (
                "performance:plan_list",
                studio_kwargs,
            ),
            "add_reminder": (
                "tasks:task_create",
                studio_kwargs,
            ),
            "measurements": (
                "costumes:measurement_roster",
                class_kwargs,
            ),
            "costumes": (
                "costumes:costume_list",
                class_kwargs,
            ),
        }

    route = mapping.get(key)

    if not route:
        return ""

    name, kwargs = route

    return _safe_reverse(
        name,
        kwargs=kwargs,
    )


@register.simple_tag
def dashboard_quick_links(
    user,
    studio,
    dashboard_kind,
    class_instance=None,
    performance_plan=None,
):
    dashboard_type = DASHBOARD_TYPE_MAP.get(
        dashboard_kind
    )

    if (
        dashboard_type is None
        or user is None
        or studio is None
    ):
        return []

    preference = (
        DashboardPreference.objects
        .filter(
            user=user,
            studio=studio,
            dashboard_type=dashboard_type,
        )
        .first()
    )

    layout = (
        preference.layout
        if preference
        else {}
    )

    normalized = (
        normalize_dashboard_quick_links(
            layout,
            dashboard_kind,
        )
    )

    output = []

    for definition in quick_link_definitions(
        dashboard_kind
    ):
        key = definition["key"]

        if not normalized[
            "enabled"
        ].get(
            key,
            False,
        ):
            continue

        url = _builtin_url(
            key,
            dashboard_kind=dashboard_kind,
            studio=studio,
            class_instance=class_instance,
            performance_plan=performance_plan,
        )

        if not url:
            continue

        output.append(
            {
                "key": key,
                "label": definition["label"],
                "icon": definition["icon"],
                "url": url,
                "external": False,
                "custom": False,
            }
        )

    for row in normalized["custom"]:
        if not (
            row["label"]
            and row["url"]
        ):
            continue

        output.append(
            {
                "key": "",
                "label": row["label"],
                "icon": "↗",
                "url": row["url"],
                "external": row["url"].startswith(
                    (
                        "http://",
                        "https://",
                    )
                ),
                "custom": True,
            }
        )

    return output
