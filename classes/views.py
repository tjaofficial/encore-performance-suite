from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib import messages
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from django.contrib.auth.decorators import login_required
from django.db import transaction, IntegrityError
from django.db.models.deletion import ProtectedError, RestrictedError
from django.db.models import (
    Case,
    Count,
    ExpressionWrapper,
    F,
    FloatField,
    IntegerField,
    Q,
    Value,
    When,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from urllib.parse import parse_qs, urlencode, urlparse

from accounts.dashboard_layouts import normalize_class_dashboard_layout
from accounts.models import DashboardPreference
from accounts.list_preferences import paginate_list, resolve_list_sort
from enrollments.models import Enrollment
from attendance.models import AttendanceRecord
from studios.models import Studio
from resources.models import ClassResource
from students.models import Student, StaffStudentNote
from evaluations.models import StudentEvaluation
from performance.models import ChoreographyPlan
from tasks.models import Task
from tasks.services import visible_tasks_for_user

from .forms import EncoreClassForm, StudioClassMeetingFormSet
from .models import Class, ClassLevel, ClassType, Season


def _youtube_thumbnail_url(url):
    if not url:
        return ""

    try:
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        video_id = ""

        if host in {
            "youtu.be",
            "www.youtu.be",
        }:
            video_id = parsed.path.strip("/").split("/")[0]

        elif host in {
            "youtube.com",
            "www.youtube.com",
            "m.youtube.com",
        }:
            if parsed.path == "/watch":
                video_id = (
                    parse_qs(parsed.query)
                    .get("v", [""])[0]
                )

            elif parsed.path.startswith("/shorts/"):
                parts = parsed.path.strip("/").split("/")
                video_id = parts[1] if len(parts) > 1 else ""

            elif parsed.path.startswith("/embed/"):
                parts = parsed.path.strip("/").split("/")
                video_id = parts[1] if len(parts) > 1 else ""

            elif parsed.path.startswith("/live/"):
                parts = parsed.path.strip("/").split("/")
                video_id = parts[1] if len(parts) > 1 else ""

        video_id = (
            video_id
            .split("?")[0]
            .split("&")[0]
            .strip()
        )

        if video_id:
            return (
                "https://i.ytimg.com/vi/"
                f"{video_id}/hqdefault.jpg"
            )

    except (
        TypeError,
        ValueError,
        IndexError,
    ):
        return ""

    return ""


def _workspace_role(request, studio):
    role = request.session.get(
        "encore_workspace_role"
    )

    studio_slug = request.session.get(
        "encore_workspace_studio_slug"
    )

    if studio_slug != studio.slug:
        return None

    if (
        request.user.is_superuser
        and role == "administrator"
    ):
        return role

    if role not in {
        "administrator",
        "teacher",
    }:
        return None

    if request.user.studio_memberships.filter(
        studio=studio,
        role=role,
        is_active=True,
    ).exists():
        return role

    return None


def _teacher_can_access_class(
    user,
    class_instance,
):
    return (
        class_instance.instructor.user_id
        == user.id
        or (
            class_instance.assistant_instructor_id
            and class_instance.assistant_instructor.user_id
            == user.id
        )
    )


def _can_manage_class(
    request,
    studio,
    class_instance=None,
):
    role = _workspace_role(
        request,
        studio,
    )

    if role == "administrator":
        return role

    if (
        role == "teacher"
        and class_instance is not None
        and _teacher_can_access_class(
            request.user,
            class_instance,
        )
    ):
        return role

    return None


CLASS_LIST_COLUMN_OPTIONS = [
    ("class_id", "Class ID"),
    ("name", "Class Name"),
    ("type", "Class Type"),
    ("level", "Level"),
    ("season", "Season"),
    ("instructor", "Instructor"),
    ("assistant", "Assistant"),
    ("schedule", "Schedule"),
    ("room", "Room"),
    ("age", "Age Range"),
    ("enrollment", "Enrollment"),
    ("waitlist", "Waitlist"),
    ("available", "Available"),
    ("capacity", "Capacity"),
    ("performance", "Performance"),
    ("registration", "Registration"),
    ("registration_window", "Registration Dates"),
    ("dress_code", "Dress Code"),
    ("tuition", "Tuition"),
    ("status", "Status"),
]

CLASS_LIST_DEFAULT_COLUMNS = [
    "class_id",
    "name",
    "type",
    "level",
    "season",
    "instructor",
    "schedule",
    "age",
    "enrollment",
    "registration",
]

CLASS_CARD_FIELD_OPTIONS = [
    ("type", "Class Type"),
    ("level", "Level"),
    ("season", "Season"),
    ("instructor", "Instructor"),
    ("assistant", "Assistant"),
    ("schedule", "Schedule"),
    ("room", "Room"),
    ("age", "Age Range"),
    ("enrollment", "Enrollment"),
    ("waitlist", "Waitlist"),
    ("available", "Available"),
    ("capacity", "Capacity"),
    ("performance", "Performance"),
    ("registration", "Registration"),
    ("registration_window", "Registration Dates"),
    ("dress_code", "Dress Code"),
    ("tuition", "Tuition"),
    ("status", "Status"),
]

CLASS_CARD_DEFAULT_FIELDS = [
    "type",
    "season",
    "instructor",
    "schedule",
    "age",
    "enrollment",
    "registration",
]


def _class_list_preference(request, studio):
    preference, _created = DashboardPreference.objects.get_or_create(
        user=request.user,
        studio=studio,
        dashboard_type=DashboardPreference.DashboardType.CLASS,
        defaults={"layout": {}},
    )

    layout = dict(preference.layout or {})
    class_list_settings = dict(layout.get("class_list") or {})

    valid_columns = {key for key, _label in CLASS_LIST_COLUMN_OPTIONS}
    valid_card_fields = {key for key, _label in CLASS_CARD_FIELD_OPTIONS}

    columns = [
        key
        for key in class_list_settings.get(
            "table_columns",
            CLASS_LIST_DEFAULT_COLUMNS,
        )
        if key in valid_columns
    ]
    if not columns:
        columns = list(CLASS_LIST_DEFAULT_COLUMNS)

    card_fields = [
        key
        for key in class_list_settings.get(
            "card_fields",
            CLASS_CARD_DEFAULT_FIELDS,
        )
        if key in valid_card_fields
    ]

    return preference, {
        "table_columns": columns,
        "card_fields": card_fields,
    }


def _safe_class_list_return(request, studio):
    candidate = str(
        request.POST.get("next")
        or request.GET.get("next")
        or ""
    ).strip()

    if candidate and url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidate

    return reverse(
        "classes:class_list",
        kwargs={"studio_slug": studio.slug},
    )


@login_required
def class_list(request, studio_slug):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    role = _workspace_role(
        request,
        studio,
    )

    if role not in {
        "administrator",
        "teacher",
    }:
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    today = timezone.localdate()

    archive_mode = (
        request.GET.get("archive", "").strip().lower()
        == "past"
    )

    requested_view = request.GET.get(
        "view",
        "",
    ).strip()

    if requested_view in {
        "cards",
        "table",
    }:
        view_mode = requested_view
        request.session[
            "encore_class_list_view_v2"
        ] = view_mode
    else:
        view_mode = request.session.get(
            "encore_class_list_view_v2",
            "table",
        )
        if view_mode not in {
            "cards",
            "table",
        }:
            view_mode = "table"

    _preference, list_preferences = (
        _class_list_preference(
            request,
            studio,
        )
    )

    search = request.GET.get(
        "q",
        "",
    ).strip()

    season_id = request.GET.get(
        "season",
        "",
    ).strip()

    type_id = request.GET.get(
        "type",
        "",
    ).strip()

    instructor_id = request.GET.get(
        "instructor",
        "",
    ).strip()

    status = request.GET.get(
        "status",
        "",
    ).strip()

    classes = (
        Class.objects
        .filter(
            studio=studio,
        )
        .select_related(
            "season",
            "class_type",
            "level",
            "instructor",
            "assistant_instructor",
            "default_location",
        )
        .prefetch_related(
            "meeting_times__room",
        )
        .annotate(
            active_enrollment_count=Count(
                "enrollments",
                filter=Q(
                    enrollments__status=Enrollment.Status.ACTIVE,
                ),
                distinct=True,
            ),
            waitlist_count=Count(
                "enrollments",
                filter=Q(
                    enrollments__status=Enrollment.Status.WAITLISTED,
                ),
                distinct=True,
            ),
        )
        .annotate(
            available_count=ExpressionWrapper(
                F("capacity")
                - F("active_enrollment_count"),
                output_field=IntegerField(),
            ),
            capacity_percent_sort=Case(
                When(
                    capacity__gt=0,
                    then=ExpressionWrapper(
                        (
                            F("active_enrollment_count")
                            * Value(100.0)
                        )
                        / F("capacity"),
                        output_field=FloatField(),
                    ),
                ),
                default=Value(0.0),
                output_field=FloatField(),
            ),
            status_sort=Case(
                When(
                    is_active=True,
                    registration_open=True,
                    then=Value(0),
                ),
                When(
                    is_active=True,
                    then=Value(1),
                ),
                default=Value(2),
                output_field=IntegerField(),
            ),
        )
    )

    current_workspace_filter = (
        Q(is_active=True)
        & Q(season__is_active=True)
        & Q(season__end_date__gte=today)
        & Q(class_type__is_active=True)
        & Q(instructor__is_active=True)
    )

    if archive_mode:
        classes = classes.exclude(
            current_workspace_filter
        )
    else:
        classes = classes.filter(
            current_workspace_filter
        )

    if role == "teacher":
        classes = classes.filter(
            Q(
                instructor__user=request.user
            )
            | Q(
                assistant_instructor__user=request.user
            )
        ).distinct()

    if search:
        classes = classes.filter(
            Q(
                class_id__icontains=search
            )
            | Q(
                name__icontains=search
            )
            | Q(
                description__icontains=search
            )
            | Q(
                class_type__name__icontains=search
            )
            | Q(
                level__name__icontains=search
            )
            | Q(
                instructor__first_name__icontains=search
            )
            | Q(
                instructor__last_name__icontains=search
            )
        )

    if season_id:
        classes = classes.filter(
            season_id=season_id,
        )

    if type_id:
        classes = classes.filter(
            class_type_id=type_id,
        )

    if (
        instructor_id
        and role == "administrator"
    ):
        classes = classes.filter(
            Q(
                instructor_id=instructor_id
            )
            | Q(
                assistant_instructor_id=instructor_id
            )
        )

    if status == "active":
        classes = classes.filter(
            is_active=True,
        )
    elif status == "inactive":
        classes = classes.filter(
            is_active=False,
        )
    elif status == "registration_open":
        classes = classes.filter(
            registration_open=True,
        )
    elif status == "registration_closed":
        classes = classes.filter(
            registration_open=False,
        )

    sort_fields = {
        "class_id": (
            "class_id",
            "name",
        ),
        "name": (
            "name",
            "class_id",
        ),
        "type": (
            "class_type__name",
            "name",
        ),
        "age": (
            "min_age",
            "max_age",
            "name",
        ),
        "level": (
            "level__number",
            "level__name",
            "name",
        ),
        "season": (
            "season__start_date",
            "name",
        ),
        "instructor": (
            "instructor__last_name",
            "instructor__first_name",
            "name",
        ),
        "enrollment": (
            "active_enrollment_count",
            "name",
        ),
        "waitlist": (
            "waitlist_count",
            "name",
        ),
        "available": (
            "available_count",
            "name",
        ),
        "capacity": (
            "capacity_percent_sort",
            "name",
        ),
        "status": (
            "status_sort",
            "name",
        ),
    }

    sort_key, direction = resolve_list_sort(
        request,
        studio,
        "classes",
        sort_fields.keys(),
        default_sort="name",
        default_direction="asc",
    )

    if sort_key not in sort_fields:
        sort_key = "name"

    selected_sort_fields = list(
        sort_fields[sort_key]
    )

    if direction == "desc":
        selected_sort_fields = [
            f"-{field}"
            for field
            in selected_sort_fields
        ]

    classes = classes.order_by(
        *selected_sort_fields
    )

    filtered_classes = classes

    if archive_mode:
        seasons = (
            Season.objects
            .filter(
                studio=studio,
            )
            .filter(
                Q(end_date__lt=today)
                | Q(is_active=False)
                | Q(
                    classes__in=filtered_classes.values("pk")
                )
            )
            .distinct()
            .order_by(
                "-start_date",
                "name",
            )
        )

        class_types = (
            ClassType.objects
            .filter(
                studio=studio,
                classes__in=filtered_classes.values("pk"),
            )
            .distinct()
            .order_by("name")
        )

        instructors = (
            studio.instructors
            .filter(
                Q(primary_classes__in=filtered_classes.values("pk"))
                | Q(assistant_classes__in=filtered_classes.values("pk"))
            )
            .distinct()
            .order_by(
                "last_name",
                "first_name",
            )
            if role == "administrator"
            else []
        )
    else:
        seasons = (
            Season.objects
            .filter(
                studio=studio,
                is_active=True,
                end_date__gte=today,
            )
            .order_by(
                "start_date",
                "name",
            )
        )

        class_types = (
            ClassType.objects
            .filter(
                studio=studio,
                is_active=True,
            )
            .order_by("name")
        )

        instructors = (
            studio.instructors
            .filter(
                is_active=True,
            )
            .order_by(
                "last_name",
                "first_name",
            )
            if role == "administrator"
            else []
        )

    page_obj, pagination_context = paginate_list(
        request,
        studio,
        "classes",
        filtered_classes,
        default_page_size=50,
    )
    classes = page_obj.object_list

    class_rows = []

    for class_instance in classes:
        remaining = max(
            class_instance.available_count,
            0,
        )

        percent_full = round(
            class_instance.capacity_percent_sort
        )

        active_meetings = [
            meeting
            for meeting in class_instance.meeting_times.all()
            if meeting.is_active
        ]

        meeting_labels = []
        room_labels = []

        for meeting in active_meetings:
            meeting_labels.append(
                (
                    f"{meeting.get_day_of_week_display()} "
                    f"{meeting.start_time.strftime('%-I:%M %p')}"
                )
            )
            if (
                meeting.room_id
                and meeting.room.name not in room_labels
            ):
                room_labels.append(
                    meeting.room.name
                )

        class_rows.append(
            {
                "class": class_instance,
                "remaining": remaining,
                "percent_full": percent_full,
                "meeting_label": (
                    ", ".join(meeting_labels)
                    if meeting_labels
                    else "No schedule"
                ),
                "room_label": (
                    ", ".join(room_labels)
                    if room_labels
                    else (
                        class_instance.default_location.name
                        if class_instance.default_location_id
                        else "—"
                    )
                ),
            }
        )

    base_query = {
        "q": search,
        "season": season_id,
        "type": type_id,
        "instructor": instructor_id,
        "status": status,
        "view": view_mode,
        "archive": (
            "past"
            if archive_mode
            else ""
        ),
        "page_size": pagination_context[
            "page_size"
        ],
    }

    def query_url(**changes):
        values = {
            key: value
            for key, value
            in base_query.items()
            if value not in {
                "",
                None,
            }
        }

        values.update(
            {
                key: value
                for key, value
                in changes.items()
                if value not in {
                    "",
                    None,
                }
            }
        )

        for key, value in changes.items():
            if value in {
                "",
                None,
            }:
                values.pop(
                    key,
                    None,
                )

        return (
            f"?{urlencode(values)}"
            if values
            else ""
        )

    column_map = dict(
        CLASS_LIST_COLUMN_OPTIONS
    )
    table_columns = []

    for key in list_preferences[
        "table_columns"
    ]:
        label = column_map[key]
        sort_config = sort_fields.get(key)

        next_direction = (
            "desc"
            if (
                sort_key == key
                and direction == "asc"
            )
            else "asc"
        )

        table_columns.append(
            {
                "key": key,
                "label": label,
                "url": (
                    query_url(
                        sort=key,
                        direction=next_direction,
                    )
                    if sort_config
                    else ""
                ),
                "is_active": (
                    bool(sort_config)
                    and sort_key == key
                ),
                "direction": (
                    direction
                    if sort_key == key
                    else ""
                ),
            }
        )

    card_view_url = query_url(
        view="cards",
        sort=sort_key,
        direction=direction,
    )

    table_view_url = query_url(
        view="table",
        sort=sort_key,
        direction=direction,
    )

    reset_query = urlencode(
        {
            "view": view_mode,
            **(
                {"archive": "past"}
                if archive_mode
                else {}
            ),
        }
    )

    current_or_past_url = (
        reverse(
            "classes:class_list",
            kwargs={
                "studio_slug": studio.slug,
            },
        )
        + (
            "?archive=past&view=table"
            if not archive_mode
            else "?view=table"
        )
    )

    active_levels = list(
        ClassLevel.objects
        .filter(
            studio=studio,
            is_active=True,
        )
        .order_by(
            "number",
            "name",
        )
    )

    active_types = list(
        ClassType.objects
        .filter(
            studio=studio,
            is_active=True,
        )
        .order_by("name")
    )

    active_instructors = list(
        studio.instructors
        .filter(
            is_active=True,
        )
        .order_by(
            "last_name",
            "first_name",
        )
    )

    active_locations = list(
        studio.locations
        .filter(
            is_active=True,
        )
        .order_by(
            "-is_primary",
            "name",
        )
    )

    bulk_seasons = list(
        (
            Season.objects
            .filter(
                studio=studio,
            )
            if archive_mode
            else Season.objects.filter(
                studio=studio,
                is_active=True,
                end_date__gte=today,
            )
        ).order_by(
            "-start_date",
            "name",
        )
    )

    bulk_edit_fields = [
        {
            "key": "name",
            "label": "Class Name",
            "input": "text",
        },
        {
            "key": "class_type",
            "label": "Class Type",
            "input": "select",
            "choices": [
                {
                    "value": item.pk,
                    "label": item.name,
                }
                for item in active_types
            ],
        },
        {
            "key": "level",
            "label": "Level",
            "input": "select",
            "choices": (
                [
                    {
                        "value": "__none__",
                        "label": "No level / mixed level",
                    }
                ]
                + [
                    {
                        "value": item.pk,
                        "label": (
                            f"Level {item.number} — "
                            f"{item.name}"
                        ),
                    }
                    for item in active_levels
                ]
            ),
        },
        {
            "key": "season",
            "label": "Season",
            "input": "select",
            "choices": [
                {
                    "value": item.pk,
                    "label": item.name,
                }
                for item in bulk_seasons
            ],
        },
        {
            "key": "instructor",
            "label": "Instructor",
            "input": "select",
            "choices": [
                {
                    "value": item.pk,
                    "label": item.full_name,
                }
                for item in active_instructors
            ],
        },
        {
            "key": "assistant_instructor",
            "label": "Assistant Instructor",
            "input": "select",
            "choices": (
                [
                    {
                        "value": "__none__",
                        "label": "No assistant",
                    }
                ]
                + [
                    {
                        "value": item.pk,
                        "label": item.full_name,
                    }
                    for item in active_instructors
                ]
            ),
        },
        {
            "key": "default_location",
            "label": "Default Location",
            "input": "select",
            "choices": (
                [
                    {
                        "value": "__none__",
                        "label": "No default location",
                    }
                ]
                + [
                    {
                        "value": item.pk,
                        "label": item.name,
                    }
                    for item in active_locations
                ]
            ),
        },
        {
            "key": "capacity",
            "label": "Capacity",
            "input": "number",
            "min": 1,
            "step": 1,
        },
        {
            "key": "min_age",
            "label": "Minimum Age",
            "input": "number_or_blank",
            "min": 0,
            "step": "0.25",
        },
        {
            "key": "max_age",
            "label": "Maximum Age",
            "input": "number_or_blank",
            "min": 0,
            "step": "0.25",
        },
        {
            "key": "registration_opens",
            "label": "Registration Start Date",
            "input": "date_or_blank",
        },
        {
            "key": "registration_closes",
            "label": "Registration End Date",
            "input": "date_or_blank",
        },
        {
            "key": "is_performance_class",
            "label": "Performance Class",
            "input": "select",
            "choices": [
                {
                    "value": "__none__",
                    "label": "Unknown / Not Confirmed",
                },
                {
                    "value": "true",
                    "label": "Yes — Performance Class",
                },
                {
                    "value": "false",
                    "label": "No — Non-Performance Class",
                },
            ],
        },
        {
            "key": "registration_open",
            "label": "Online Registration",
            "input": "select",
            "choices": [
                {
                    "value": "true",
                    "label": "Open",
                },
                {
                    "value": "false",
                    "label": "Closed / Permission Required",
                },
            ],
        },
        {
            "key": "allow_drop_ins",
            "label": "Allow Drop-ins",
            "input": "select",
            "choices": [
                {
                    "value": "true",
                    "label": "Yes",
                },
                {
                    "value": "false",
                    "label": "No",
                },
            ],
        },
        {
            "key": "is_active",
            "label": "Class Status",
            "input": "select",
            "choices": [
                {
                    "value": "true",
                    "label": "Active",
                },
                {
                    "value": "false",
                    "label": "Inactive",
                },
            ],
        },
    ]

    return render(
        request,
        "classes/class_list.html",
        {
            "studio": studio,
            "role": role,
            "class_rows": class_rows,
            "seasons": seasons,
            "class_types": class_types,
            "instructors": instructors,
            "view_mode": view_mode,
            "archive_mode": archive_mode,
            "sort_key": sort_key,
            "sort_direction": direction,
            "table_columns": table_columns,
            "card_fields": list_preferences[
                "card_fields"
            ],
            "available_table_columns": [
                {
                    "key": key,
                    "label": label,
                }
                for key, label
                in CLASS_LIST_COLUMN_OPTIONS
            ],
            "available_card_fields": [
                {
                    "key": key,
                    "label": label,
                }
                for key, label
                in CLASS_CARD_FIELD_OPTIONS
            ],
            "bulk_edit_fields": bulk_edit_fields,
            "card_view_url": card_view_url,
            "table_view_url": table_view_url,
            "current_or_past_url": (
                current_or_past_url
            ),
            "reset_url": (
                reverse(
                    "classes:class_list",
                    kwargs={
                        "studio_slug": studio.slug,
                    },
                )
                + f"?{reset_query}"
            ),
            "filters": {
                "q": search,
                "season": season_id,
                "type": type_id,
                "instructor": instructor_id,
                "status": status,
            },
            **pagination_context,
        },
    )


@login_required
@transaction.atomic
def class_list_settings(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if (
        request.method != "POST"
        or _workspace_role(
            request,
            studio,
        )
        not in {
            "administrator",
            "teacher",
        }
    ):
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    preference, current = (
        _class_list_preference(
            request,
            studio,
        )
    )

    valid_columns = {
        key
        for key, _label
        in CLASS_LIST_COLUMN_OPTIONS
    }
    valid_card_fields = {
        key
        for key, _label
        in CLASS_CARD_FIELD_OPTIONS
    }

    def load_list(name):
        try:
            value = json.loads(
                request.POST.get(
                    name,
                    "[]",
                )
            )
        except (
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ):
            value = []

        return (
            value
            if isinstance(
                value,
                list,
            )
            else []
        )

    columns = [
        str(value)
        for value
        in load_list(
            "table_columns_json"
        )
        if str(value)
        in valid_columns
    ]

    card_fields = [
        str(value)
        for value
        in load_list(
            "card_fields_json"
        )
        if str(value)
        in valid_card_fields
    ]

    if not columns:
        columns = current[
            "table_columns"
        ]

    layout = dict(
        preference.layout
        or {}
    )
    layout["class_list"] = {
        "table_columns": columns,
        "card_fields": card_fields,
    }

    preference.layout = layout
    preference.save(
        update_fields=[
            "layout",
            "updated_at",
        ]
    )

    messages.success(
        request,
        "Class Manager display settings updated.",
    )

    return redirect(
        _safe_class_list_return(
            request,
            studio,
        )
    )


@login_required
@transaction.atomic
def class_bulk_edit(
    request,
    studio_slug,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if (
        request.method != "POST"
        or _workspace_role(
            request,
            studio,
        )
        != "administrator"
    ):
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    try:
        selected_ids = json.loads(
            request.POST.get(
                "selected_ids_json",
                "[]",
            )
        )
    except (
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ):
        selected_ids = []

    selected_ids = [
        int(value)
        for value
        in selected_ids
        if str(value).isdigit()
    ]

    if not selected_ids:
        messages.error(
            request,
            "Select at least one class to edit.",
        )
        return redirect(
            _safe_class_list_return(
                request,
                studio,
            )
        )

    if request.POST.get("action") == "delete_classes":
        # Never trust client-selected IDs or relationship counts. Scope to studio
        # and protect history even if a client bypasses the confirmation dialog.
        if len(set(selected_ids)) > 500:
            messages.error(request, "Delete at most 500 selected classes at once.")
            return redirect(_safe_class_list_return(request, studio))

        selected = list(
            Class.objects.select_for_update()
            .filter(studio=studio, pk__in=set(selected_ids))
        )
        if not selected:
            messages.error(request, "No matching classes were found.")
            return redirect(_safe_class_list_return(request, studio))

        deleted_count = 0
        blocked = []
        # Only meeting-time records can be discarded along with a class.
        # Every other reverse relationship, including enrollments and billing,
        # blocks removal. This is deliberately conservative.
        for instance in selected:
            reasons = []
            for relation in Class._meta.related_objects:
                accessor = relation.get_accessor_name()
                if accessor == "meeting_times":
                    continue
                try:
                    related = getattr(instance, accessor)
                    has_related = (related.exists() if hasattr(related, "exists")
                                   else related is not None)
                except (AttributeError, ValueError):
                    has_related = True
                if has_related:
                    reasons.append(relation.related_model._meta.verbose_name_plural)
            if reasons:
                blocked.append(instance.name)
                continue
            try:
                # A separate savepoint keeps a protected record from rolling
                # back successful, unrelated deletions.
                with transaction.atomic():
                    instance.delete()
                deleted_count += 1
            except (ProtectedError, RestrictedError, IntegrityError):
                blocked.append(instance.name)

        if deleted_count:
            messages.success(
                request,
                f"Deleted {deleted_count} unused class"
                f"{'es' if deleted_count != 1 else ''}.",
            )
        if blocked:
            messages.warning(
                request,
                f"Kept {len(blocked)} class(es) with related data or protected "
                "records. No related history was deleted. Examples: "
                + ", ".join(blocked[:5])
                + ("…" if len(blocked) > 5 else ""),
            )
        return redirect(_safe_class_list_return(request, studio))

    field_name = str(
        request.POST.get(
            "field",
            "",
        )
    ).strip()

    raw_value = str(
        request.POST.get(
            "value",
            "",
        )
    ).strip()

    standardize_name = (
        request.POST.get(
            "standardize_name",
            "",
        )
        == "1"
    )

    allowed_fields = {
        "name",
        "class_type",
        "level",
        "season",
        "instructor",
        "assistant_instructor",
        "default_location",
        "capacity",
        "min_age",
        "max_age",
        "registration_opens",
        "registration_closes",
        "is_performance_class",
        "registration_open",
        "allow_drop_ins",
        "is_active",
    }

    if field_name not in allowed_fields:
        messages.error(
            request,
            "That field cannot be bulk edited.",
        )
        return redirect(
            _safe_class_list_return(
                request,
                studio,
            )
        )

    classes = list(
        Class.objects
        .filter(
            studio=studio,
            pk__in=selected_ids,
        )
        .select_related(
            "season",
            "class_type",
            "level",
        )
    )

    if not classes:
        messages.error(
            request,
            "No matching classes were found.",
        )
        return redirect(
            _safe_class_list_return(
                request,
                studio,
            )
        )

    relation_config = {
        "class_type": (
            ClassType.objects.filter(
                studio=studio,
                is_active=True,
            ),
            False,
        ),
        "level": (
            ClassLevel.objects.filter(
                studio=studio,
                is_active=True,
            ),
            True,
        ),
        "season": (
            Season.objects.filter(
                studio=studio,
            ),
            False,
        ),
        "instructor": (
            studio.instructors.filter(
                is_active=True,
            ),
            False,
        ),
        "assistant_instructor": (
            studio.instructors.filter(
                is_active=True,
            ),
            True,
        ),
        "default_location": (
            studio.locations.filter(
                is_active=True,
            ),
            True,
        ),
    }

    relation_value = None

    if field_name in relation_config:
        queryset, nullable = (
            relation_config[
                field_name
            ]
        )

        if (
            raw_value == "__none__"
            and nullable
        ):
            relation_value = None
        elif raw_value.isdigit():
            relation_value = (
                queryset
                .filter(
                    pk=int(
                        raw_value
                    ),
                )
                .first()
            )
            if relation_value is None:
                messages.error(
                    request,
                    "The selected value is not available.",
                )
                return redirect(
                    _safe_class_list_return(
                        request,
                        studio,
                    )
                )
        else:
            messages.error(
                request,
                "Choose a valid value.",
            )
            return redirect(
                _safe_class_list_return(
                    request,
                    studio,
                )
            )

    def parse_bool(value):
        if value == "true":
            return True
        if value == "false":
            return False
        raise ValueError

    updated = 0

    for class_instance in classes:
        if field_name == "name":
            if not raw_value:
                messages.error(
                    request,
                    "Class name cannot be blank.",
                )
                return redirect(
                    _safe_class_list_return(
                        request,
                        studio,
                    )
                )
            class_instance.name = raw_value

        elif field_name in relation_config:
            setattr(
                class_instance,
                field_name,
                relation_value,
            )

        elif field_name == "capacity":
            try:
                value = int(
                    raw_value
                )
            except ValueError:
                value = 0

            if value < 1:
                messages.error(
                    request,
                    "Capacity must be at least 1.",
                )
                return redirect(
                    _safe_class_list_return(
                        request,
                        studio,
                    )
                )

            class_instance.capacity = value

        elif field_name in {
            "min_age",
            "max_age",
        }:
            if raw_value == "__blank__":
                value = None
            else:
                try:
                    value = Decimal(
                        raw_value
                    )
                except InvalidOperation:
                    messages.error(
                        request,
                        "Enter a valid age.",
                    )
                    return redirect(
                        _safe_class_list_return(
                            request,
                            studio,
                        )
                    )

                if value < 0:
                    messages.error(
                        request,
                        "Age cannot be negative.",
                    )
                    return redirect(
                        _safe_class_list_return(
                            request,
                            studio,
                        )
                    )

            setattr(
                class_instance,
                field_name,
                value,
            )

        elif field_name in {
            "registration_opens",
            "registration_closes",
        }:
            if raw_value == "__blank__":
                value = None
            else:
                try:
                    value = datetime.strptime(
                        raw_value,
                        "%Y-%m-%d",
                    ).date()
                except ValueError:
                    messages.error(
                        request,
                        "Enter a valid registration date.",
                    )
                    return redirect(
                        _safe_class_list_return(
                            request,
                            studio,
                        )
                    )

            setattr(
                class_instance,
                field_name,
                value,
            )

        elif field_name == (
            "is_performance_class"
        ):
            if raw_value == "__none__":
                class_instance.is_performance_class = (
                    None
                )
            else:
                try:
                    class_instance.is_performance_class = (
                        parse_bool(
                            raw_value
                        )
                    )
                except ValueError:
                    messages.error(
                        request,
                        "Choose a valid performance setting.",
                    )
                    return redirect(
                        _safe_class_list_return(
                            request,
                            studio,
                        )
                    )

        elif field_name in {
            "registration_open",
            "allow_drop_ins",
            "is_active",
        }:
            try:
                setattr(
                    class_instance,
                    field_name,
                    parse_bool(
                        raw_value
                    ),
                )
            except ValueError:
                messages.error(
                    request,
                    "Choose a valid Yes/No value.",
                )
                return redirect(
                    _safe_class_list_return(
                        request,
                        studio,
                    )
                )

        if (
            standardize_name
            and field_name
            in {
                "class_type",
                "level",
            }
            and class_instance.season.end_date
            >= timezone.localdate()
        ):
            class_instance.name = (
                class_instance
                .standardized_name()
            )

        class_instance.full_clean()
        class_instance.save()
        updated += 1

    messages.success(
        request,
        (
            f"{updated} class"
            f"{'' if updated == 1 else 'es'} updated."
        ),
    )

    return redirect(
        _safe_class_list_return(
            request,
            studio,
        )
    )


@login_required
def class_detail(request, studio_slug, class_id):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    class_instance = get_object_or_404(
        Class.objects
        .select_related(
            "season",
            "class_type",
            "instructor",
            "instructor__user",
            "assistant_instructor",
            "assistant_instructor__user",
            "default_location",
        )
        .prefetch_related(
            "meeting_times",
            "prerequisites",
        ),
        pk=class_id,
        studio=studio,
    )

    role = _can_manage_class(
        request,
        studio,
        class_instance,
    )

    if role is None:
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    active_enrollments = list(
        class_instance.enrollments
        .filter(
            status=Enrollment.Status.ACTIVE
        )
        .select_related("student")
        .order_by(
            "student__last_name",
            "student__first_name",
        )
    )

    waitlisted = list(
        class_instance.enrollments
        .filter(
            status=Enrollment.Status.WAITLISTED
        )
        .select_related("student")
        .order_by(
            "student__last_name",
            "student__first_name",
        )
    )

    class_resource_qs = (
        ClassResource.objects
        .filter(
            studio=studio,
            class_instance=class_instance,
            is_active=True,
        )
        .order_by(
            "sort_order",
            "-created_at",
        )
    )

    class_videos = list(
        class_resource_qs.filter(
            resource_type=ClassResource.ResourceType.VIDEO,
        )[:6]
    )

    for video in class_videos:
        video.youtube_thumbnail_url = (
            _youtube_thumbnail_url(
                video.external_url
            )
        )

    class_music = list(
        class_resource_qs.filter(
            resource_type=ClassResource.ResourceType.MUSIC,
        )[:5]
    )

    performance_plan = (
        ChoreographyPlan.objects
        .filter(
            studio=studio,
            class_instance=class_instance,
        )
        .first()
    )

    class_tasks = list(
        visible_tasks_for_user(
            request.user,
            studio,
            role,
        )
        .filter(
            class_instance=class_instance,
        )
        .exclude(
            completions__user=request.user,
        )
        .distinct()[:5]
    )

    meetings = list(
        class_instance.meeting_times
        .filter(is_active=True)
        .order_by(
            "day_of_week",
            "start_time",
        )
    )

    age_label = "No restriction"

    if (
        class_instance.min_age is not None
        and class_instance.max_age is not None
    ):
        if class_instance.min_age == class_instance.max_age:
            age_label = (
                f"Age {class_instance.min_age}"
            )
        else:
            age_label = (
                f"Ages {class_instance.min_age}"
                f"–{class_instance.max_age}"
            )
    elif class_instance.min_age is not None:
        age_label = (
            f"Ages {class_instance.min_age}+"
        )
    elif class_instance.max_age is not None:
        age_label = (
            f"Up to age "
            f"{class_instance.max_age}"
        )

    preference = (
        DashboardPreference.objects
        .filter(
            user=request.user,
            studio=studio,
            dashboard_type=DashboardPreference.DashboardType.CLASS,
        )
        .first()
    )

    dashboard_layout = (
        normalize_class_dashboard_layout(
            preference.layout
            if preference
            else {}
        )
    )

    card_template_map = {
        "roster": "classes/cards/roster.html",
        "attendance": "classes/cards/attendance.html",
        "videos": "classes/cards/videos.html",
        "music": "classes/cards/music.html",
        "tasks": "classes/cards/tasks.html",
        "schedule": "classes/cards/schedule.html",
        "performance": "classes/cards/performance.html",
        "drawing_board": "classes/cards/drawing_board.html",
        "waitlist": "classes/cards/waitlist.html",
        "stopwatch": "dashboard/widgets/stopwatch.html",
    }

    dashboard_cards = []

    for card in dashboard_layout["cards"]:
        if not card["enabled"]:
            continue

        if (
            card["key"] == "waitlist"
            and not waitlisted
        ):
            continue

        dashboard_cards.append(
            {
                **card,
                "template": card_template_map[
                    card["key"]
                ],
            }
        )

    return render(
        request,
        "classes/class_detail.html",
        {
            "studio": studio,
            "role": role,
            "class_instance": class_instance,
            "active_enrollments": active_enrollments,
            "waitlisted": waitlisted,
            "class_videos": class_videos,
            "class_music": class_music,
            "video_count": class_resource_qs.filter(
                resource_type=ClassResource.ResourceType.VIDEO,
            ).count(),
            "music_count": class_resource_qs.filter(
                resource_type=ClassResource.ResourceType.MUSIC,
            ).count(),
            "performance_plan": performance_plan,
            "class_tasks": class_tasks,
            "meetings": meetings,
            "age_label": age_label,
            "dashboard_cards": dashboard_cards,
        },
    )


@login_required
@require_POST
def class_student_notes_save(request, studio_slug, class_id, student_id):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    klass = get_object_or_404(Class, pk=class_id, studio=studio)
    if _can_manage_class(request, studio, klass) is None:
        return JsonResponse({'error': 'Access denied'}, status=403)
    student = get_object_or_404(Student, pk=student_id, studio=studio)
    if not Enrollment.objects.filter(student=student, class_instance=klass).exists():
        return JsonResponse({'error': 'Student is not enrolled in this class'}, status=404)
    try:
        payload = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({'error': 'Invalid request'}, status=400)
    scope = payload.get('scope')
    if scope not in ('class', 'profile') or not isinstance(payload.get('text'), str):
        return JsonResponse({'error': 'Invalid note'}, status=400)
    if len(payload['text']) > 10000:
        return JsonResponse({'error': 'Note is too long'}, status=400)
    if scope == 'profile' and _workspace_role(request, studio) != 'administrator':
        return JsonResponse({'error': 'Profile notes require administrator access'}, status=403)
    note_class = klass if scope == 'class' else None
    with transaction.atomic():
        note, _ = StaffStudentNote.objects.select_for_update().get_or_create(
            student=student, class_instance=note_class,
            defaults={'studio': studio, 'updated_by': request.user},
        )
        version = str(payload.get('version') or '')
        if version and version != note.updated_at.isoformat():
            return JsonResponse({'error': 'This note changed in another session. Refresh before editing.'}, status=409)
        note.text = payload['text']
        note.updated_by = request.user
        note.save(update_fields=['text', 'updated_by', 'updated_at'])
    return JsonResponse({'saved': True, 'version': note.updated_at.isoformat()})


@login_required
def class_student_detail(
    request,
    studio_slug,
    class_id,
    student_id,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    class_instance = get_object_or_404(
        Class.objects.select_related(
            "season",
            "class_type",
            "instructor",
            "instructor__user",
            "assistant_instructor",
            "assistant_instructor__user",
            "default_location",
        ),
        pk=class_id,
        studio=studio,
    )

    role = _can_manage_class(
        request,
        studio,
        class_instance,
    )

    if role is None:
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    enrollment = get_object_or_404(
        Enrollment.objects.select_related(
            "student",
            "student__family",
            "class_instance",
        ),
        class_instance=class_instance,
        student_id=student_id,
    )

    student = enrollment.student
    class_note = StaffStudentNote.objects.filter(student=student, class_instance=class_instance).first()
    profile_note = StaffStudentNote.objects.filter(student=student, class_instance__isnull=True).first()

    attendance_records = (
        AttendanceRecord.objects
        .filter(
            student=student,
            session__class_instance=class_instance,
        )
        .select_related(
            "session",
            "marked_by",
        )
        .order_by(
            "-session__session_date",
            "-session__start_time",
        )
    )

    attendance_total = attendance_records.count()

    present_like = attendance_records.filter(
        status__in=[
            AttendanceRecord.Status.PRESENT,
            AttendanceRecord.Status.LATE,
            AttendanceRecord.Status.LEFT_EARLY,
        ]
    ).count()

    absent_count = attendance_records.filter(
        status=AttendanceRecord.Status.ABSENT,
    ).count()

    late_count = attendance_records.filter(
        status=AttendanceRecord.Status.LATE,
    ).count()

    excused_count = attendance_records.filter(
        status=AttendanceRecord.Status.EXCUSED,
    ).count()

    attendance_percentage = (
        round(
            (
                present_like
                / attendance_total
            )
            * 100
        )
        if attendance_total
        else None
    )

    evaluations = (
        StudentEvaluation.objects
        .filter(
            studio=studio,
            student=student,
            class_instance=class_instance,
        )
        .select_related(
            "instructor",
            "template",
        )
        .prefetch_related(
            "ratings__criterion",
        )
        .order_by(
            "-evaluation_date",
            "-created_at",
        )
    )

    latest_evaluation = evaluations.first()

    student_tasks = list(
        visible_tasks_for_user(
            request.user,
            studio,
            role,
        )
        .filter(
            Q(
                student=student,
            )
            | Q(
                assignments__student=student,
                is_student_facing=True,
            ),
            class_instance=class_instance,
        )
        .exclude(
            completions__user=request.user,
        )
        .distinct()[:6]
    )

    relevant_resources = list(
        ClassResource.objects
        .filter(
            studio=studio,
            class_instance=class_instance,
            is_active=True,
        )
        .order_by(
            "resource_type",
            "sort_order",
            "-created_at",
        )[:6]
    )

    return render(
        request,
        "classes/class_student_detail.html",
        {
            "studio": studio,
            "role": role,
            "class_instance": class_instance,
            "student": student,
            "class_note": class_note,
            "profile_note": profile_note,
            "enrollment": enrollment,
            "attendance_records": attendance_records[:8],
            "attendance_total": attendance_total,
            "present_like": present_like,
            "absent_count": absent_count,
            "late_count": late_count,
            "excused_count": excused_count,
            "attendance_percentage": attendance_percentage,
            "evaluations": evaluations[:5],
            "latest_evaluation": latest_evaluation,
            "student_tasks": student_tasks,
            "relevant_resources": relevant_resources,
        },
    )


@login_required
@transaction.atomic
def class_create(request, studio_slug):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if _workspace_role(request, studio) != "administrator":
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    class_instance = Class(studio=studio)

    if request.method == "POST":
        form = EncoreClassForm(
            request.POST,
            instance=class_instance,
            studio=studio,
        )

        formset = StudioClassMeetingFormSet(
            request.POST,
            instance=class_instance,
            studio=studio,
        )

        if form.is_valid() and formset.is_valid():
            class_instance = form.save(
                commit=False
            )
            class_instance.studio = studio
            class_instance.full_clean()
            class_instance.save()
            form.save_m2m()

            formset.instance = class_instance
            meetings = formset.save(commit=False)

            for deleted in formset.deleted_objects:
                deleted.delete()

            for meeting in meetings:
                meeting.full_clean()
                meeting.save()

            messages.success(
                request,
                f"{class_instance.name} was created.",
            )

            return redirect(
                "classes:class_detail",
                studio_slug=studio.slug,
                class_id=class_instance.pk,
            )
    else:
        form = EncoreClassForm(
            instance=class_instance,
            studio=studio,
        )

        formset = StudioClassMeetingFormSet(
            instance=class_instance,
            studio=studio,
        )

    return render(
        request,
        "classes/class_form.html",
        {
            "studio": studio,
            "role": "administrator",
            "form": form,
            "formset": formset,
            "class_instance": None,
            "page_title": "Add Class",
        },
    )


@login_required
@transaction.atomic
def class_edit(request, studio_slug, class_id):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if _workspace_role(request, studio) != "administrator":
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    class_instance = get_object_or_404(
        Class,
        pk=class_id,
        studio=studio,
    )

    if request.method == "POST":
        form = EncoreClassForm(
            request.POST,
            instance=class_instance,
            studio=studio,
        )

        formset = StudioClassMeetingFormSet(
            request.POST,
            instance=class_instance,
            studio=studio,
        )

        if form.is_valid() and formset.is_valid():
            class_instance = form.save(
                commit=False
            )
            class_instance.full_clean()
            class_instance.save()
            form.save_m2m()

            meetings = formset.save(commit=False)

            for deleted in formset.deleted_objects:
                deleted.delete()

            for meeting in meetings:
                meeting.full_clean()
                meeting.save()

            messages.success(
                request,
                f"{class_instance.name} was updated.",
            )

            return redirect(
                "classes:class_detail",
                studio_slug=studio.slug,
                class_id=class_instance.pk,
            )
    else:
        form = EncoreClassForm(
            instance=class_instance,
            studio=studio,
        )

        formset = StudioClassMeetingFormSet(
            instance=class_instance,
            studio=studio,
        )

    return render(
        request,
        "classes/class_form.html",
        {
            "studio": studio,
            "role": "administrator",
            "form": form,
            "formset": formset,
            "class_instance": class_instance,
            "page_title": "Edit Class",
        },
    )


@login_required
def class_approval_codes(request, studio_slug, class_id):
    """Admin-only issuance and secure replacement of class approval codes."""
    import logging
    from django import forms
    from django.conf import settings
    from django.urls import reverse
    from django.utils.html import escape
    from registration_portal.approval_codes import issue
    from registration_portal.models import ClassApprovalCode
    from communications.studio_email import send_studio_email

    logger = logging.getLogger(__name__)
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if _workspace_role(request, studio) != "administrator":
        return render(request, "dashboard/access_denied.html", {"studio": studio}, status=403)
    klass = get_object_or_404(Class, studio=studio, pk=class_id)

    class ApprovalForm(forms.Form):
        email = forms.EmailField(label="Parent / guardian email")
        valid_days = forms.ChoiceField(
            choices=[(1, "1 day"), (3, "3 days"), (7, "7 days"), (14, "14 days")], initial=7
        )

    def email_code(row, plaintext):
        registration_url = (
            settings.ENCORE_PUBLIC_BASE_URL.rstrip("/")
            + reverse("registration_portal:public_registration_home", kwargs={"studio_slug": studio.slug})
        )
        safe_studio = escape(studio.name)
        safe_class = escape(klass.name)
        safe_code = escape(plaintext)
        expires = timezone.localtime(row.expires_at).strftime("%B %d, %Y at %I:%M %p %Z")
        html = (
            '<div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;line-height:1.6">'
            f'<h2>{safe_studio} — Class Registration Approval</h2>'
            '<p>You have been approved to register for the following class after an in-person assessment:</p>'
            f'<p><strong>{safe_class}</strong></p>'
            '<p>Enter this personal approval code when selecting the class during registration:</p>'
            f'<p style="font-size:24px;font-weight:bold;letter-spacing:2px">{safe_code}</p>'
            f'<p><strong>Expires:</strong> {escape(expires)}</p>'
            f'<p><a href="{escape(registration_url)}">Continue to registration</a></p>'
            '<p>Use the email address this message was sent to. This code does not guarantee a class spot; '
            'normal capacity and payment requirements still apply.</p>'
            f'<p>Questions? Reply to this email to reach {safe_studio}.</p>'
            '<p>If you were not expecting this invitation, please contact the studio.</p></div>'
        )
        plain = (
            f"{studio.name} — Class Registration Approval\n\n"
            f"You have been approved to register for {klass.name} after an in-person assessment.\n"
            f"Personal code: {plaintext}\nExpires: {expires}\n"
            f"Registration: {registration_url}\n\n"
            "Use the email address this message was sent to. Capacity and payment rules still apply.\n"
            f"Reply to this email with questions for {studio.name}."
        )
        # Never store a readable approval code in Email Activity (sensitive=True).
        return send_studio_email(
            studio=studio, to=[row.parent_email],
            subject=f"{studio.name}: Registration approval for {klass.name}",
            html_body=html, text_body=plain, sensitive=True,
            tags={"message_type": "registration_approval_code", "approval_id": str(row.pk)},
        )

    form = ApprovalForm(request.POST or None)
    displayed_code = None
    if request.method == "POST" and request.POST.get("revoke_id"):
        count = ClassApprovalCode.objects.filter(
            pk=request.POST["revoke_id"], studio=studio,
            class_instance=klass, used_at__isnull=True,
            revoked_at__isnull=True,
        ).update(revoked_at=timezone.now())
        if count:
            messages.success(request, "Approval code revoked.")
        return redirect("classes:class_approval_codes", studio_slug=studio.slug, class_id=klass.pk)

    if request.method == "POST" and request.POST.get("resend_id"):
        old = ClassApprovalCode.objects.filter(
            pk=request.POST["resend_id"], studio=studio, class_instance=klass,
            used_at__isnull=True, revoked_at__isnull=True,
            claimed_session__isnull=True, expires_at__gt=timezone.now(),
        ).first()
        if not old:
            messages.error(request, "This code cannot be replaced. Generate a new authorization if appropriate.")
        else:
            # The old secret is intentionally unrecoverable. A resend issues a new code.
            days = max(1, min(14, (old.expires_at - timezone.now()).days + 1))
            new_row, replacement = issue(studio, klass, old.parent_email, request.user, days=days)
            try:
                email_code(new_row, replacement)
            except Exception:
                logger.exception("Failed to send replacement approval code (id=%s)", new_row.pk)
                new_row.revoked_at = timezone.now()
                new_row.save(update_fields=["revoked_at"])
                messages.error(request, "Email delivery failed. The original approval code is still valid.")
            else:
                old.revoked_at = timezone.now()
                old.save(update_fields=["revoked_at"])
                messages.success(request, "Replacement code emailed. The original code was revoked.")
        return redirect("classes:class_approval_codes", studio_slug=studio.slug, class_id=klass.pk)

    if request.method == "POST" and form.is_valid():
        try:
            row, displayed_code = issue(
                studio, klass, form.cleaned_data["email"], request.user,
                days=int(form.cleaned_data["valid_days"]),
            )
            try:
                email_code(row, displayed_code)
            except Exception:
                logger.exception("Failed to email new approval code (id=%s)", row.pk)
                messages.warning(request, "Code created, but email delivery failed. Copy the code below and share it securely.")
            else:
                messages.success(request, "Code generated and email accepted by Encore's email provider. Check Email Activity for delivery confirmation.")
            form = ApprovalForm()
        except ValueError as exc:
            form.add_error(None, str(exc))

    return render(request, "classes/class_approval_codes.html", {
        "studio": studio, "class_instance": klass, "form": form,
        "displayed_code": displayed_code,
        "codes": ClassApprovalCode.objects.filter(studio=studio, class_instance=klass).select_related("issued_by")[:100],
        "role": "administrator",
    })


@login_required
def approval_codes_overview(request, studio_slug):
    """Admin-only landing page for choosing a class to issue approval codes."""
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if _workspace_role(request, studio) != "administrator":
        return render(request, "dashboard/access_denied.html", {"studio": studio}, status=403)

    qs = Class.objects.filter(studio=studio).select_related("season")
    search = (request.GET.get("q") or "").strip()[:100]
    if search:
        qs = qs.filter(Q(name__icontains=search) | Q(season__name__icontains=search))
    mode = (request.GET.get("mode") or "approval").strip()
    if mode == "approval":
        qs = qs.filter(registration_mode=Class.RegistrationMode.APPROVAL)
    elif mode == "online":
        qs = qs.filter(registration_mode=Class.RegistrationMode.ONLINE)
    else:
        mode = "all"
    qs = qs.order_by("name", "pk")
    return render(request, "classes/approval_codes_overview.html", {
        "studio": studio, "role": "administrator", "classes": qs[:250],
        "search": search, "selected_mode": mode,
    })
