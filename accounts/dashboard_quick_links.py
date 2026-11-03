from copy import deepcopy
from urllib.parse import urlsplit


MAX_CUSTOM_QUICK_LINKS = 4
# Explicit allowlist so saved dashboard preferences cannot insert arbitrary markup.
QUICK_LINK_ICONS = (
    "external-link", "calendar-days", "music-2", "video", "users",
    "book-open", "clipboard-check", "shirt", "list-checks", "bell",
    "star", "heart", "link", "home", "clock-3", "key-round",
    "graduation-cap", "megaphone", "ruler", "clapperboard", "settings",
)


QUICK_LINK_DEFINITIONS = {
    "admin": [
        {
            "key": "approval_codes",
            "label": "Approval Codes",
            "description": "Issue in-person class registration approvals.",
            "icon": "key-round",
            "default": False,
        },
        {
            "key": "calendar",
            "label": "Calendar",
            "description": "Built-in Encore shortcut.",
            "icon": "calendar-days",
            "default": True,
        },
        {
            "key": "classes",
            "label": "Class Manager",
            "description": "Built-in Encore shortcut.",
            "icon": "book-open",
            "default": True,
        },
        {
            "key": "students",
            "label": "Students",
            "description": "Built-in Encore shortcut.",
            "icon": "users",
            "default": True,
        },
        {
            "key": "instructors",
            "label": "Instructors",
            "description": "Built-in Encore shortcut.",
            "icon": "graduation-cap",
            "default": False,
        },
        {
            "key": "announcements",
            "label": "Announcements",
            "description": "Built-in Encore shortcut.",
            "icon": "megaphone",
            "default": False,
        },
        {
            "key": "tasks",
            "label": "Tasks",
            "description": "Built-in Encore shortcut.",
            "icon": "list-checks",
            "default": True,
        },
    ],
    "teacher": [
        {
            "key": "calendar",
            "label": "Calendar",
            "description": "Built-in Encore shortcut.",
            "icon": "calendar-days",
            "default": True,
        },
        {
            "key": "add_reminder",
            "label": "Add Reminder",
            "description": "Built-in Encore shortcut.",
            "icon": "bell-plus",
            "default": True,
        },
        {
            "key": "log_extra_work",
            "label": "Log Extra Work",
            "description": "Built-in Encore shortcut.",
            "icon": "clock-3",
            "default": False,
        },
        {
            "key": "announcements",
            "label": "Announcements",
            "description": "Built-in Encore shortcut.",
            "icon": "megaphone",
            "default": False,
        },
    ],
    "class": [
        {
            "key": "attendance",
            "label": "Attendance",
            "description": "Built-in Encore shortcut.",
            "icon": "clipboard-check",
            "default": True,
        },
        {
            "key": "music",
            "label": "Music",
            "description": "Built-in Encore shortcut.",
            "icon": "music-2",
            "default": True,
        },
        {
            "key": "videos",
            "label": "Videos",
            "description": "Built-in Encore shortcut.",
            "icon": "video",
            "default": True,
        },
        {
            "key": "performance",
            "label": "Dances",
            "description": "Built-in Encore shortcut.",
            "icon": "clapperboard",
            "default": True,
        },
        {
            "key": "add_reminder",
            "label": "Add Reminder",
            "description": "Built-in Encore shortcut.",
            "icon": "bell-plus",
            "default": True,
        },
        {
            "key": "measurements",
            "label": "Measurements",
            "description": "Built-in Encore shortcut.",
            "icon": "ruler",
            "default": True,
        },
        {
            "key": "costumes",
            "label": "Costumes",
            "description": "Built-in Encore shortcut.",
            "icon": "shirt",
            "default": True,
        },
    ],
}


def quick_link_definitions(dashboard_kind):
    return deepcopy(
        QUICK_LINK_DEFINITIONS.get(
            dashboard_kind,
            [],
        )
    )


def default_dashboard_quick_links(dashboard_kind):
    definitions = quick_link_definitions(
        dashboard_kind
    )

    return {
        "enabled": {
            item["key"]: bool(item["default"])
            for item in definitions
        },
        "custom": [
            {
                "label": "",
                "url": "",
                "icon": "external-link",
            }
            for _index in range(
                MAX_CUSTOM_QUICK_LINKS
            )
        ],
    }


def _clean_custom_url(value):
    value = str(value or "").strip()

    if not value:
        return ""

    if value.startswith("/") and not value.startswith("//"):
        return value[:1000]

    parsed = urlsplit(value)

    if parsed.scheme.lower() in {
        "http",
        "https",
    } and parsed.netloc:
        return value[:1000]

    return ""


def _clean_custom_links(values):
    if not isinstance(values, list):
        values = []

    cleaned = []

    for row in values[:MAX_CUSTOM_QUICK_LINKS]:
        if not isinstance(row, dict):
            row = {}

        label = str(
            row.get(
                "label",
                "",
            )
        ).strip()[:80]

        url = _clean_custom_url(
            row.get(
                "url",
                "",
            )
        )

        if bool(label) != bool(url):
            label = ""
            url = ""

        icon = str(row.get("icon") or "external-link").strip()
        if icon not in QUICK_LINK_ICONS:
            icon = "external-link"
        cleaned.append(
            {
                "label": label,
                "url": url,
                "icon": icon,
            }
        )

    while len(cleaned) < MAX_CUSTOM_QUICK_LINKS:
        cleaned.append(
            {
                "label": "",
                "url": "",
                "icon": "external-link",
            }
        )

    return cleaned


def normalize_dashboard_quick_links(
    source,
    dashboard_kind,
):
    defaults = default_dashboard_quick_links(
        dashboard_kind
    )

    if not isinstance(source, dict):
        return defaults

    if isinstance(
        source.get("quick_links"),
        dict,
    ):
        raw = source["quick_links"]
    elif (
        "enabled" in source
        or "custom" in source
    ):
        raw = source
    else:
        raw = {}

    enabled = dict(
        defaults["enabled"]
    )

    raw_enabled = raw.get(
        "enabled",
        {},
    )

    if isinstance(raw_enabled, dict):
        for key in enabled:
            if key in raw_enabled:
                enabled[key] = bool(
                    raw_enabled[key]
                )

    # Backward compatibility with the old class/teacher
    # quick_actions boolean dictionary.
    legacy = source.get(
        "quick_actions",
        {},
    )

    if (
        not raw_enabled
        and isinstance(
            legacy,
            dict,
        )
    ):
        for key in enabled:
            if key in legacy:
                enabled[key] = bool(
                    legacy[key]
                )

    return {
        "enabled": enabled,
        "custom": _clean_custom_links(
            raw.get(
                "custom",
                [],
            )
        ),
    }


def quick_link_editor_options(
    source,
    dashboard_kind,
):
    normalized = normalize_dashboard_quick_links(
        source,
        dashboard_kind,
    )

    rows = []

    for item in quick_link_definitions(
        dashboard_kind
    ):
        rows.append(
            {
                **item,
                "selected": normalized[
                    "enabled"
                ].get(
                    item["key"],
                    False,
                ),
            }
        )

    return rows
