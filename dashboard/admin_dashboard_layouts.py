from accounts.dashboard_quick_links import (
    default_dashboard_quick_links,
    normalize_dashboard_quick_links,
)

ADMIN_SNAPSHOT_METRICS = [
    {"key": "student_records", "label": "Student Records", "description": "Total student records in the studio."},
    {"key": "active_students", "label": "Active Students", "description": "Students currently marked active."},
    {"key": "active_classes", "label": "Active Classes", "description": "Classes currently marked active."},
    {"key": "active_enrollments", "label": "Active Enrollments", "description": "Current active class enrollments."},
    {"key": "instructors", "label": "Instructors", "description": "Active faculty members."},
    {"key": "waitlisted", "label": "Waitlisted", "description": "Students currently waiting for a class."},
]

DEFAULT_ADMIN_SNAPSHOT_METRICS = [
    "student_records",
    "active_classes",
    "instructors",
    "waitlisted",
]

ADMIN_DASHBOARD_CARDS = [
    {
        "key": "studio_snapshot",
        "label": "Studio Snapshot",
        "description": "A fixed-size overview of your selected studio metrics.",
        "default_width": "full",
        "default_height": 1,
        "locked": True,
        "required": True,
        "template": "dashboard/admin_cards/studio_snapshot.html",
    },
    {
        "key": "capacity",
        "label": "Classes Filling Up",
        "description": "Classes approaching or reaching capacity.",
        "default_width": "half",
        "default_height": 1,
        "locked": False,
        "required": False,
        "template": "dashboard/admin_cards/capacity.html",
    },
    {
        "key": "upcoming_events",
        "label": "Upcoming Events",
        "description": "Studio events in the next 30 days.",
        "default_width": "half",
        "default_height": 1,
        "locked": False,
        "required": False,
        "template": "dashboard/admin_cards/upcoming_events.html",
    },
    {
        "key": "recent_enrollments",
        "label": "Recent Enrollments",
        "description": "Newest student enrollment activity.",
        "default_width": "half",
        "default_height": 2,
        "locked": False,
        "required": False,
        "template": "dashboard/admin_cards/recent_enrollments.html",
    },
    {
        "key": "upcoming_birthdays",
        "label": "Upcoming Birthdays",
        "description": "Student birthdays coming up in the next 30 days.",
        "default_width": "half",
        "default_height": 2,
        "locked": False,
        "required": False,
        "template": "dashboard/admin_cards/upcoming_birthdays.html",
    },
]

VALID_ADMIN_WIDTHS = {"quarter", "half", "full"}
VALID_ADMIN_HEIGHTS = {1, 2}
SNAPSHOT_METRIC_KEYS = {item["key"] for item in ADMIN_SNAPSHOT_METRICS}


def _normalize_snapshot_metrics(values):
    if not isinstance(values, list):
        values = []

    clean = []

    for value in values:
        key = str(value)

        if key in SNAPSHOT_METRIC_KEYS and key not in clean:
            clean.append(key)

    if not clean:
        clean = list(DEFAULT_ADMIN_SNAPSHOT_METRICS)

    return clean[:6]


def default_admin_dashboard_layout():
    return {
        "version": 3,
        "snapshot_metrics": list(DEFAULT_ADMIN_SNAPSHOT_METRICS),
        "quick_links": default_dashboard_quick_links(
            "admin"
        ),
        "cards": [
            {
                "key": card["key"],
                "enabled": True,
                "order": order,
                "width": card["default_width"],
                "height": card["default_height"],
            }
            for order, card in enumerate(ADMIN_DASHBOARD_CARDS, start=1)
        ],
    }


def normalize_admin_dashboard_layout(layout):
    defaults = default_admin_dashboard_layout()
    incoming = {}

    if isinstance(layout, dict):
        for card in layout.get("cards", []):
            if isinstance(card, dict) and card.get("key"):
                incoming[card["key"]] = card

    definitions = {item["key"]: item for item in ADMIN_DASHBOARD_CARDS}
    normalized = []

    for fallback in defaults["cards"]:
        definition = definitions[fallback["key"]]
        saved = incoming.get(fallback["key"], {})

        if definition["locked"]:
            width = definition["default_width"]
            height = definition["default_height"]
        else:
            width = saved.get("width", fallback["width"])

            if width not in VALID_ADMIN_WIDTHS:
                width = fallback["width"]

            try:
                height = int(saved.get("height", fallback["height"]))
            except (TypeError, ValueError):
                height = fallback["height"]

            if height not in VALID_ADMIN_HEIGHTS:
                height = fallback["height"]

        try:
            order = int(saved.get("order", fallback["order"]))
        except (TypeError, ValueError):
            order = fallback["order"]

        normalized.append(
            {
                "key": fallback["key"],
                "enabled": True if definition["required"] else bool(saved.get("enabled", fallback["enabled"])),
                "order": order,
                "width": width,
                "height": height,
            }
        )

    normalized.sort(key=lambda card: (card["order"], card["key"]))

    for index, card in enumerate(normalized, start=1):
        card["order"] = index

    snapshot_metrics = (
        layout.get("snapshot_metrics", defaults["snapshot_metrics"])
        if isinstance(layout, dict)
        else defaults["snapshot_metrics"]
    )

    return {
        "version": 3,
        "snapshot_metrics": _normalize_snapshot_metrics(snapshot_metrics),
        "quick_links": normalize_dashboard_quick_links(
            layout,
            "admin",
        ),
        # Quick Links intentionally are NOT a dashboard card.
        "cards": normalized,
    }


def admin_dashboard_render_cards(layout):
    normalized = normalize_admin_dashboard_layout(layout)
    definitions = {item["key"]: item for item in ADMIN_DASHBOARD_CARDS}
    result = []

    for card in normalized["cards"]:
        if not card["enabled"]:
            continue

        definition = definitions[card["key"]]
        rendered = {
            **card,
            "label": definition["label"],
            "description": definition["description"],
            "template": definition["template"],
            "locked": definition["locked"],
        }

        if card["key"] == "studio_snapshot":
            rendered["snapshot_metrics"] = normalized["snapshot_metrics"]

        result.append(rendered)

    return result


def admin_dashboard_editor_cards(layout):
    normalized = normalize_admin_dashboard_layout(layout)
    definitions = {item["key"]: item for item in ADMIN_DASHBOARD_CARDS}

    return [
        {
            **card,
            "label": definitions[card["key"]]["label"],
            "description": definitions[card["key"]]["description"],
            "locked": definitions[card["key"]]["locked"],
            "required": definitions[card["key"]]["required"],
        }
        for card in normalized["cards"]
    ]


def admin_snapshot_metric_options(layout):
    normalized = normalize_admin_dashboard_layout(layout)
    selected = set(normalized["snapshot_metrics"])

    return [
        {
            **metric,
            "selected": metric["key"] in selected,
        }
        for metric in ADMIN_SNAPSHOT_METRICS
    ]
