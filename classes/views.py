from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
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
from urllib.parse import parse_qs, urlencode, urlparse

from accounts.dashboard_layouts import normalize_class_dashboard_layout
from accounts.models import DashboardPreference
from enrollments.models import Enrollment
from attendance.models import AttendanceRecord
from studios.models import Studio
from resources.models import ClassResource
from students.models import Student
from evaluations.models import StudentEvaluation
from performance.models import ChoreographyPlan
from tasks.models import Task
from tasks.services import visible_tasks_for_user

from .forms import EncoreClassForm, StudioClassMeetingFormSet
from .models import Class, ClassType, Season


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
            "encore_class_list_view"
        ] = view_mode
    else:
        view_mode = request.session.get(
            "encore_class_list_view",
            "cards",
        )

        if view_mode not in {
            "cards",
            "table",
        }:
            view_mode = "cards"

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

    sort_key = request.GET.get(
        "sort",
        "name",
    ).strip()

    direction = request.GET.get(
        "direction",
        "asc",
    ).strip()

    if direction not in {
        "asc",
        "desc",
    }:
        direction = "asc"

    classes = (
        Class.objects
        .filter(
            studio=studio,
        )
        .select_related(
            "season",
            "class_type",
            "instructor",
            "assistant_instructor",
            "default_location",
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
        "season": (
            "season__name",
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

    seasons = Season.objects.filter(
        studio=studio,
    ).order_by(
        "-start_date",
        "name",
    )

    class_types = ClassType.objects.filter(
        studio=studio,
    ).order_by("name")

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

    class_rows = []

    for class_instance in classes:
        remaining = max(
            class_instance.available_count,
            0,
        )

        percent_full = round(
            class_instance.capacity_percent_sort
        )

        class_rows.append(
            {
                "class": class_instance,
                "remaining": remaining,
                "percent_full": percent_full,
            }
        )

    base_query = {
        "q": search,
        "season": season_id,
        "type": type_id,
        "instructor": instructor_id,
        "status": status,
        "view": view_mode,
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

        return (
            f"?{urlencode(values)}"
            if values
            else ""
        )

    table_columns = []

    for key, label in [
        ("class_id", "Class ID"),
        ("name", "Class Name"),
        ("type", "Type"),
        ("season", "Season"),
        ("instructor", "Instructor"),
        ("enrollment", "Enrollment"),
        ("waitlist", "Waitlist"),
        ("available", "Available"),
        ("capacity", "Capacity"),
        ("status", "Status"),
    ]:
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
                "url": query_url(
                    sort=key,
                    direction=next_direction,
                ),
                "is_active": sort_key == key,
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
        }
    )

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
            "sort_key": sort_key,
            "sort_direction": direction,
            "table_columns": table_columns,
            "card_view_url": card_view_url,
            "table_view_url": table_view_url,
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
        },
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
