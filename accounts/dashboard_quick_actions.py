CLASS_QUICK_ACTIONS = [
    {
        "key": "attendance",
        "label": "Attendance",
        "default_enabled": True,
    },
    {
        "key": "music",
        "label": "Music",
        "default_enabled": True,
    },
    {
        "key": "videos",
        "label": "Videos",
        "default_enabled": True,
    },
    {
        "key": "performance",
        "label": "Performance",
        "default_enabled": True,
    },
    {
        "key": "add_reminder",
        "label": "Add Reminder",
        "default_enabled": True,
    },
]


def default_class_quick_actions():
    return {
        item["key"]: item["default_enabled"]
        for item in CLASS_QUICK_ACTIONS
    }


def normalize_class_quick_actions(value):
    defaults = default_class_quick_actions()

    if not isinstance(value, dict):
        return defaults

    return {
        key: bool(
            value.get(
                key,
                default,
            )
        )
        for key, default in defaults.items()
    }


def class_quick_action_choices(value):
    normalized = normalize_class_quick_actions(
        value
    )

    return [
        {
            **item,
            "enabled": normalized[
                item["key"]
            ],
        }
        for item in CLASS_QUICK_ACTIONS
    ]
