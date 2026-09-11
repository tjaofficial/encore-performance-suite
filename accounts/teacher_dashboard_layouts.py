from accounts.dashboard_quick_links import (
    default_dashboard_quick_links,
    normalize_dashboard_quick_links,
    quick_link_editor_options,
)


TEACHER_CARD_DEFINITIONS = {
    "today_classes": {
        "label": "Today's Classes",
        "description": (
            "Today's schedule, selected class details, roster, "
            "and attendance access."
        ),
        "default_width": "half",
        "default_height": 2,
    },
    "tasks": {
        "label": "Reminders / To-Do",
        "description": (
            "Your open teacher tasks, reminders, and assigned work."
        ),
        "default_width": "half",
        "default_height": 2,
    },
    "dances": {
        "label": "Dances",
        "description": (
            "Quick access to dances organized by the classes you teach."
        ),
        "default_width": "half",
        "default_height": 2,
    },
}

VALID_WIDTHS = {
    "quarter",
    "half",
    "full",
}

VALID_HEIGHTS = {
    1,
    2,
}


def default_teacher_dashboard_layout():
    quick_links = default_dashboard_quick_links(
        "teacher"
    )

    return {
        "version": 4,
        "quick_links": quick_links,
        "quick_actions": dict(
            quick_links["enabled"]
        ),
        "cards": [
            {
                "key": "today_classes",
                "enabled": True,
                "order": 1,
                "width": "half",
                "height": 2,
            },
            {
                "key": "tasks",
                "enabled": True,
                "order": 2,
                "width": "half",
                "height": 2,
            },
            {
                "key": "dances",
                "enabled": True,
                "order": 3,
                "width": "half",
                "height": 2,
            },
        ],
    }


def normalize_teacher_dashboard_layout(layout):
    defaults = default_teacher_dashboard_layout()

    if not isinstance(layout, dict):
        layout = {}

    incoming = {}

    for row in layout.get(
        "cards",
        [],
    ):
        if (
            isinstance(row, dict)
            and row.get("key")
            in TEACHER_CARD_DEFINITIONS
        ):
            incoming[row["key"]] = row

    normalized_cards = []

    for fallback in defaults["cards"]:
        key = fallback["key"]
        saved = incoming.get(
            key,
            {},
        )

        width = saved.get(
            "width",
            fallback["width"],
        )

        # Migrate the temporary 3/4 option back into the
        # same standard size system used everywhere else.
        if width == "three_quarter":
            width = "half"

        if width not in VALID_WIDTHS:
            width = fallback["width"]

        try:
            height = int(
                saved.get(
                    "height",
                    fallback["height"],
                )
            )
        except (
            TypeError,
            ValueError,
        ):
            height = fallback["height"]

        if height not in VALID_HEIGHTS:
            height = fallback["height"]

        try:
            order = int(
                saved.get(
                    "order",
                    fallback["order"],
                )
            )
        except (
            TypeError,
            ValueError,
        ):
            order = fallback["order"]

        normalized_cards.append(
            {
                "key": key,
                "enabled": bool(
                    saved.get(
                        "enabled",
                        fallback["enabled"],
                    )
                ),
                "order": order,
                "width": width,
                "height": height,
            }
        )

    normalized_cards.sort(
        key=lambda card: (
            card["order"],
            card["key"],
        )
    )

    for index, card in enumerate(
        normalized_cards,
        start=1,
    ):
        card["order"] = index

    quick_links = (
        normalize_dashboard_quick_links(
            layout,
            "teacher",
        )
    )

    return {
        "version": 4,
        "quick_links": quick_links,
        # Keep old dashboard view/template integrations alive.
        "quick_actions": dict(
            quick_links["enabled"]
        ),
        "cards": normalized_cards,
    }


def teacher_dashboard_editor_cards(layout):
    normalized = (
        normalize_teacher_dashboard_layout(
            layout
        )
    )

    rows = []

    for card in normalized["cards"]:
        definition = (
            TEACHER_CARD_DEFINITIONS[
                card["key"]
            ]
        )

        rows.append(
            {
                **card,
                "label": definition["label"],
                "description": (
                    definition["description"]
                ),
                "locked": False,
                "required": False,
            }
        )

    return rows


def teacher_quick_action_options(layout):
    return quick_link_editor_options(
        layout,
        "teacher",
    )


# Backward-compatible name still imported by onboarding_views.py.
def teacher_quick_action_choices(layout):
    return teacher_quick_action_options(
        layout
    )


def teacher_dashboard_render_cards(layout):
    normalized = (
        normalize_teacher_dashboard_layout(
            layout
        )
    )

    return [
        card
        for card in normalized["cards"]
        if card["enabled"]
    ]
