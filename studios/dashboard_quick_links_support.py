import json

from accounts.dashboard_quick_links import (
    normalize_dashboard_quick_links,
    quick_link_editor_options,
)


def parse_quick_links_post(
    request,
    *,
    dashboard_kind,
):
    try:
        raw = json.loads(
            request.POST.get(
                "quick_links_json",
                "{}",
            )
        )
    except (
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ):
        raw = {}

    return normalize_dashboard_quick_links(
        raw,
        dashboard_kind,
    )


def quick_links_context(
    layout,
    *,
    dashboard_kind,
):
    normalized = normalize_dashboard_quick_links(
        layout,
        dashboard_kind,
    )

    return {
        "quick_link_options": (
            quick_link_editor_options(
                layout,
                dashboard_kind,
            )
        ),
        "quick_links_custom": normalized["custom"],
        "quick_links_json": json.dumps(
            normalized
        ),
    }
