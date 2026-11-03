CLASS_DASHBOARD_CARDS = [
    {
        "key": "roster",
        "label": "Class Roster",
        "description": "Active students and class-specific Student Detail links.",
        "default_width": "half",
        "default_height": 1,
    },
    {
        "key": "attendance",
        "label": "Attendance",
        "description": "Attendance summary and Take Attendance shortcut.",
        "default_width": "half",
        "default_height": 1,
    },
    {
        "key": "videos",
        "label": "Class Videos",
        "description": "Recent video resources for this class.",
        "default_width": "half",
        "default_height": 1,
    },
    {
        "key": "music",
        "label": "Recent Music",
        "description": "Recent music uploads and files for this class.",
        "default_width": "half",
        "default_height": 1,
    },
    {
        "key": "tasks",
        "label": "Reminders / To-Do",
        "description": "Open reminders linked to this class.",
        "default_width": "quarter",
        "default_height": 1,
    },
    {
        "key": "schedule",
        "label": "Weekly Schedule",
        "description": "Meeting days, times, and locations.",
        "default_width": "quarter",
        "default_height": 1,
    },
    {
        "key": "performance",
        "label": "Dances",
        "description": "Class dances, choreography, staging, and performance planning.",
        "default_width": "half",
        "default_height": 1,
    },
    {
        "key": "drawing_board",
        "label": "Drawing Board",
        "description": "Visual stage formations and dancer placement for this class.",
        "default_width": "half",
        "default_height": 1,
    },
    {
        "key": "stopwatch",
        "label": "Stopwatch",
        "description": "Rehearsal stopwatch with laps and pause/resume.",
        "default_width": "quarter",
        "default_height": 2,
    },
    {
        "key": "waitlist",
        "label": "Waitlist",
        "description": "Waitlisted students when the class has a waitlist.",
        "default_width": "quarter",
        "default_height": 1,
    },
]

VALID_WIDTHS = {"quarter", "half", "full"}
VALID_HEIGHTS = {1, 2}


def default_class_dashboard_layout():
    return {
        "version": 1,
        "cards": [
            {
                "key": card["key"],
                "enabled": True,
                "order": order,
                "width": card["default_width"],
                "height": card["default_height"],
            }
            for order, card in enumerate(
                CLASS_DASHBOARD_CARDS,
                start=1,
            )
        ],
    }


def normalize_class_dashboard_layout(layout):
    defaults = default_class_dashboard_layout()
    incoming = {}

    if isinstance(layout, dict):
        for card in layout.get("cards", []):
            if isinstance(card, dict) and card.get("key"):
                incoming[card["key"]] = card

    normalized = []

    for fallback in defaults["cards"]:
        saved = incoming.get(fallback["key"], {})

        width = saved.get("width", fallback["width"])
        if width not in VALID_WIDTHS:
            width = fallback["width"]

        try:
            height = int(saved.get("height", fallback["height"]))
        except (TypeError, ValueError):
            height = fallback["height"]

        if height not in VALID_HEIGHTS:
            height = fallback["height"]
        if fallback["key"] == "stopwatch":
            height = 2

        try:
            order = int(saved.get("order", fallback["order"]))
        except (TypeError, ValueError):
            order = fallback["order"]

        normalized.append(
            {
                "key": fallback["key"],
                "enabled": bool(saved.get("enabled", fallback["enabled"])),
                "order": order,
                "width": width,
                "height": height,
            }
        )

    normalized.sort(key=lambda card: (card["order"], card["key"]))

    for index, card in enumerate(normalized, start=1):
        card["order"] = index

    return {"version": 1, "cards": normalized}


def class_dashboard_editor_cards(layout):
    normalized = normalize_class_dashboard_layout(layout)
    definitions = {
        item["key"]: item
        for item in CLASS_DASHBOARD_CARDS
    }

    return [
        {
            **card,
            "label": definitions[card["key"]]["label"],
            "description": definitions[card["key"]]["description"],
            "min_height": 2 if card["key"] == "stopwatch" else 1,
        }
        for card in normalized["cards"]
    ]
