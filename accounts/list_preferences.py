from urllib.parse import urlencode

from django.core.paginator import Paginator

from .models import DashboardPreference


VALID_LIST_VIEW_MODES = {
    "cards",
    "table",
}

VALID_PAGE_SIZES = (
    25,
    50,
    100,
)


def _preference(request, studio):
    preference, _created = (
        DashboardPreference.objects.get_or_create(
            user=request.user,
            studio=studio,
            dashboard_type=(
                DashboardPreference.DashboardType.ADMIN
            ),
            defaults={"layout": {}},
        )
    )
    return preference


def resolve_list_view_mode(
    request,
    studio,
    preference_key,
    *,
    default="table",
):
    """
    Resolve and persist a per-user, per-studio list display mode.
    """
    if default not in VALID_LIST_VIEW_MODES:
        default = "table"

    preference = _preference(request, studio)
    layout = dict(preference.layout or {})
    saved_views = dict(
        layout.get("list_views") or {}
    )

    requested = str(
        request.GET.get("view") or ""
    ).strip().lower()

    if requested in VALID_LIST_VIEW_MODES:
        if saved_views.get(preference_key) != requested:
            saved_views[preference_key] = requested
            layout["list_views"] = saved_views
            preference.layout = layout
            preference.save(
                update_fields=[
                    "layout",
                    "updated_at",
                ]
            )

        return requested

    saved = str(
        saved_views.get(
            preference_key,
            default,
        )
        or default
    ).strip().lower()

    if saved not in VALID_LIST_VIEW_MODES:
        return default

    return saved


def resolve_list_page_size(
    request,
    studio,
    preference_key,
    *,
    default=50,
):
    """
    Persist rows-per-page independently for each manager list.
    """
    if default not in VALID_PAGE_SIZES:
        default = 50

    preference = _preference(request, studio)
    layout = dict(preference.layout or {})
    saved_sizes = dict(
        layout.get("list_page_sizes") or {}
    )

    requested = str(
        request.GET.get("page_size") or ""
    ).strip()

    if requested.isdigit():
        requested_size = int(requested)
        if requested_size in VALID_PAGE_SIZES:
            if (
                saved_sizes.get(preference_key)
                != requested_size
            ):
                saved_sizes[
                    preference_key
                ] = requested_size
                layout[
                    "list_page_sizes"
                ] = saved_sizes
                preference.layout = layout
                preference.save(
                    update_fields=[
                        "layout",
                        "updated_at",
                    ]
                )
            return requested_size

    saved = saved_sizes.get(
        preference_key,
        default,
    )

    try:
        saved = int(saved)
    except (TypeError, ValueError):
        saved = default

    if saved not in VALID_PAGE_SIZES:
        saved = default

    return saved


def _url_with(request, **changes):
    params = request.GET.copy()

    for key, value in changes.items():
        if value in {
            None,
            "",
        }:
            params.pop(key, None)
        else:
            params[key] = str(value)

    encoded = params.urlencode()
    return f"?{encoded}" if encoded else ""


def paginate_list(
    request,
    studio,
    preference_key,
    queryset,
    *,
    default_page_size=50,
):
    """
    Apply server-side pagination and return a template-ready context.
    """
    page_size = resolve_list_page_size(
        request,
        studio,
        preference_key,
        default=default_page_size,
    )

    paginator = Paginator(
        queryset,
        page_size,
    )
    page_obj = paginator.get_page(
        request.GET.get("page")
    )

    page_items = []
    for page_number in paginator.get_elided_page_range(
        page_obj.number,
        on_each_side=2,
        on_ends=1,
    ):
        is_ellipsis = (
            page_number == paginator.ELLIPSIS
        )

        page_items.append(
            {
                "label": str(page_number),
                "is_ellipsis": is_ellipsis,
                "is_current": (
                    not is_ellipsis
                    and page_number == page_obj.number
                ),
                "url": (
                    ""
                    if is_ellipsis
                    else _url_with(
                        request,
                        page=page_number,
                    )
                ),
            }
        )

    page_size_options = [
        {
            "size": size,
            "selected": size == page_size,
            "url": _url_with(
                request,
                page=None,
                page_size=size,
            ),
        }
        for size in VALID_PAGE_SIZES
    ]

    return page_obj, {
        "page_obj": page_obj,
        "page_size": page_size,
        "page_size_options": page_size_options,
        "pagination_items": page_items,
        "pagination_previous_url": (
            _url_with(
                request,
                page=page_obj.previous_page_number(),
            )
            if page_obj.has_previous()
            else ""
        ),
        "pagination_next_url": (
            _url_with(
                request,
                page=page_obj.next_page_number(),
            )
            if page_obj.has_next()
            else ""
        ),
        "pagination_start": (
            page_obj.start_index()
            if paginator.count
            else 0
        ),
        "pagination_end": (
            page_obj.end_index()
            if paginator.count
            else 0
        ),
        "pagination_total": paginator.count,
    }


def resolve_list_sort(
    request,
    studio,
    preference_key,
    valid_sort_keys,
    *,
    default_sort,
    default_direction="asc",
):
    valid_sort_keys = set(valid_sort_keys)
    preference = _preference(request, studio)
    layout = dict(preference.layout or {})
    saved = dict(layout.get("list_sorts") or {})
    current = dict(saved.get(preference_key) or {})

    requested_sort = str(request.GET.get("sort") or "").strip()
    requested_direction = str(
        request.GET.get("direction") or ""
    ).strip().lower()

    sort_key = (
        requested_sort
        if requested_sort in valid_sort_keys
        else str(current.get("sort") or default_sort)
    )
    if sort_key not in valid_sort_keys:
        sort_key = default_sort

    direction = (
        requested_direction
        if requested_direction in {"asc", "desc"}
        else str(current.get("direction") or default_direction)
    )
    if direction not in {"asc", "desc"}:
        direction = default_direction

    if requested_sort in valid_sort_keys or requested_direction in {"asc", "desc"}:
        next_value = {
            "sort": sort_key,
            "direction": direction,
        }
        if current != next_value:
            saved[preference_key] = next_value
            layout["list_sorts"] = saved
            preference.layout = layout
            preference.save(
                update_fields=[
                    "layout",
                    "updated_at",
                ]
            )

    return sort_key, direction


def list_sort_url(
    request,
    sort_key,
    current_sort,
    current_direction,
):
    params = request.GET.copy()
    params["sort"] = sort_key
    params["direction"] = (
        "desc"
        if (
            current_sort == sort_key
            and current_direction == "asc"
        )
        else "asc"
    )
    params.pop("page", None)
    encoded = params.urlencode()
    return f"?{encoded}" if encoded else ""
