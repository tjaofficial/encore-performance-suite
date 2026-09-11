from datetime import datetime, timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone

from accounts.models import DashboardPreference
from accounts.teacher_dashboard_layouts import (
    default_teacher_dashboard_layout,
    normalize_teacher_dashboard_layout,
    teacher_dashboard_render_cards,
)
from dashboard.admin_dashboard_layouts import (
    admin_dashboard_render_cards,
    default_admin_dashboard_layout,
    normalize_admin_dashboard_layout,
)
from attendance.models import AttendanceRecord, AttendanceSession
from classes.models import Class, ClassMeeting
from communications.models import Announcement
from enrollments.models import Enrollment
from families.models import Guardian
from instructors.models import Instructor
from performance.models import ChoreographyPlan
from scheduling.models import CalendarEvent
from students.models import Student
from studios.models import Studio
from tasks.services import visible_tasks_for_user
from timekeeping.models import ExtraWorkEntry


def _attendance_stats_for_student(student):
    records = AttendanceRecord.objects.filter(
        student=student,
    )

    total = records.count()

    present_like = records.filter(
        status__in=[
            AttendanceRecord.Status.PRESENT,
            AttendanceRecord.Status.LATE,
            AttendanceRecord.Status.LEFT_EARLY,
        ]
    ).count()

    absent = records.filter(
        status=AttendanceRecord.Status.ABSENT,
    ).count()

    excused = records.filter(
        status=AttendanceRecord.Status.EXCUSED,
    ).count()

    percentage = (
        round((present_like / total) * 100)
        if total
        else None
    )

    return {
        "total": total,
        "present_like": present_like,
        "absent": absent,
        "excused": excused,
        "percentage": percentage,
    }


def _selected_workspace_role(request, studio):
    """
    Respect the workspace the user actually selected instead of
    inferring the highest role from all memberships.
    """
    selected_role = request.session.get(
        "encore_workspace_role"
    )

    selected_studio = request.session.get(
        "encore_workspace_studio_slug"
    )

    if selected_studio != studio.slug:
        return None

    if (
        request.user.is_superuser
        and selected_role == "administrator"
    ):
        return "administrator"

    if selected_role not in {
        "administrator",
        "teacher",
        "family",
        "student",
    }:
        return None

    if request.user.studio_memberships.filter(
        studio=studio,
        role=selected_role,
        is_active=True,
    ).exists():
        return selected_role

    return None


def _next_class_meetings(
    student_enrollments,
    *,
    limit=8,
    days_ahead=21,
):
    """
    Convert weekly ClassMeeting definitions into the next actual
    class occurrences for the family dashboard.

    Season dates are respected.
    """
    now = timezone.localtime()
    today = now.date()
    horizon = today + timedelta(days=days_ahead)

    rows = []

    for enrollment in student_enrollments:
        class_instance = enrollment.class_instance
        season = class_instance.season

        for meeting in class_instance.meeting_times.filter(
            is_active=True,
        ).select_related("location"):
            # Find the next matching weekday from today.
            days_until = (
                meeting.day_of_week - today.weekday()
            ) % 7

            occurrence_date = today + timedelta(
                days=days_until
            )

            # Walk weekly through the horizon. This also handles a
            # meeting later today vs a meeting that already happened.
            while occurrence_date <= horizon:
                if (
                    occurrence_date >= season.start_date
                    and occurrence_date <= season.end_date
                ):
                    occurrence_dt = timezone.make_aware(
                        datetime.combine(
                            occurrence_date,
                            meeting.start_time,
                        ),
                        timezone.get_current_timezone(),
                    )

                    if occurrence_dt >= now:
                        rows.append(
                            {
                                "student": enrollment.student,
                                "class_instance": class_instance,
                                "meeting": meeting,
                                "start_at": occurrence_dt,
                            }
                        )

                occurrence_date += timedelta(days=7)

    rows.sort(
        key=lambda row: row["start_at"]
    )

    return rows[:limit]




def _admin_studio_snapshot(studio, today):
    tomorrow = today + timedelta(days=1)

    students = Student.objects.filter(
        studio=studio,
    )

    total_students = students.count()

    enrolled_ids = set(
        Enrollment.objects
        .filter(
            student__studio=studio,
            status=Enrollment.Status.ACTIVE,
        )
        .values_list("student_id", flat=True)
        .distinct()
    )

    waitlisted_only_ids = set(
        Enrollment.objects
        .filter(
            student__studio=studio,
            status=Enrollment.Status.WAITLISTED,
        )
        .exclude(student_id__in=enrolled_ids)
        .values_list("student_id", flat=True)
        .distinct()
    )

    enrolled_count = len(enrolled_ids)
    waitlisted_only_count = len(waitlisted_only_ids)
    inactive_count = max(
        0,
        total_students - enrolled_count - waitlisted_only_count,
    )

    enrolled_pct = (
        enrolled_count / total_students * 100
        if total_students
        else 0
    )
    waitlisted_pct = (
        waitlisted_only_count / total_students * 100
        if total_students
        else 0
    )

    students_starting = (
        Enrollment.objects
        .filter(
            student__studio=studio,
            status=Enrollment.Status.ACTIVE,
            class_instance__is_active=True,
            class_instance__season__start_date__in=[
                today,
                tomorrow,
            ],
        )
        .values("student_id")
        .distinct()
        .count()
    )

    birthdays = 0

    for student in students.only("birthday"):
        birthday = student.birthday

        try:
            next_birthday = birthday.replace(year=today.year)
        except ValueError:
            next_birthday = birthday.replace(
                year=today.year,
                day=28,
            )

        if next_birthday < today:
            try:
                next_birthday = birthday.replace(
                    year=today.year + 1,
                )
            except ValueError:
                next_birthday = birthday.replace(
                    year=today.year + 1,
                    day=28,
                )

        if (next_birthday - today).days <= 30:
            birthdays += 1

    classes_enrolled = (
        Class.objects
        .filter(
            studio=studio,
            is_active=True,
            enrollments__status=Enrollment.Status.ACTIVE,
        )
        .distinct()
        .count()
    )

    families_enrolled = (
        Enrollment.objects
        .filter(
            student__studio=studio,
            student__family__isnull=False,
            status=Enrollment.Status.ACTIVE,
        )
        .values("student__family_id")
        .distinct()
        .count()
    )

    primary_instructors = set(
        Class.objects
        .filter(
            studio=studio,
            is_active=True,
            instructor__is_active=True,
        )
        .values_list("instructor_id", flat=True)
    )

    assistant_instructors = set(
        Class.objects
        .filter(
            studio=studio,
            is_active=True,
            assistant_instructor__isnull=False,
            assistant_instructor__is_active=True,
        )
        .values_list("assistant_instructor_id", flat=True)
    )

    instructors_assigned = len(
        primary_instructors | assistant_instructors
    )

    waitlists_with_space = 0

    for class_instance in (
        Class.objects
        .filter(
            studio=studio,
            is_active=True,
        )
        .annotate(
            active_count=Count(
                "enrollments",
                filter=Q(
                    enrollments__status=Enrollment.Status.ACTIVE,
                ),
                distinct=True,
            ),
            waitlist_total=Count(
                "enrollments",
                filter=Q(
                    enrollments__status=Enrollment.Status.WAITLISTED,
                ),
                distinct=True,
            ),
        )
    ):
        if (
            class_instance.waitlist_total > 0
            and class_instance.active_count < class_instance.capacity
        ):
            waitlists_with_space += 1

    last_two_by_student = {}

    for record in (
        AttendanceRecord.objects
        .filter(student__studio=studio)
        .select_related("session")
        .order_by(
            "student_id",
            "-session__session_date",
            "-id",
        )
    ):
        statuses = last_two_by_student.setdefault(
            record.student_id,
            [],
        )

        if len(statuses) < 2:
            statuses.append(record.status)

    missing_consecutive = sum(
        1
        for statuses in last_two_by_student.values()
        if (
            len(statuses) == 2
            and statuses[0] == AttendanceRecord.Status.ABSENT
            and statuses[1] == AttendanceRecord.Status.ABSENT
        )
    )

    waitlisted_students = (
        Enrollment.objects
        .filter(
            student__studio=studio,
            status=Enrollment.Status.WAITLISTED,
        )
        .values("student_id")
        .distinct()
        .count()
    )

    return {
        "total_students": total_students,
        "enrolled_count": enrolled_count,
        "waitlisted_only_count": waitlisted_only_count,
        "inactive_count": inactive_count,
        "enrolled_stop": round(enrolled_pct, 3),
        "waitlisted_stop": round(
            enrolled_pct + waitlisted_pct,
            3,
        ),
        "students_starting": students_starting,
        "birthdays": birthdays,
        "classes_enrolled": classes_enrolled,
        "families_enrolled": families_enrolled,
        "missing_consecutive": missing_consecutive,
        "instructors_assigned": instructors_assigned,
        "waitlists_with_space": waitlists_with_space,
        "active_students": students.filter(is_active=True).count(),
        "active_enrollments": Enrollment.objects.filter(
            student__studio=studio,
            status=Enrollment.Status.ACTIVE,
        ).count(),
        "waitlisted_students": waitlisted_students,
    }

def _admin_today_classes(studio, today):
    weekday = today.weekday()

    meetings = (
        ClassMeeting.objects
        .filter(
            class_instance__studio=studio,
            class_instance__is_active=True,
            class_instance__season__start_date__lte=today,
            class_instance__season__end_date__gte=today,
            day_of_week=weekday,
            is_active=True,
        )
        .select_related(
            "class_instance",
            "class_instance__instructor",
            "class_instance__default_location",
            "location",
        )
        .annotate(
            enrollment_count=Count(
                "class_instance__enrollments",
                filter=Q(
                    class_instance__enrollments__status=Enrollment.Status.ACTIVE,
                ),
                distinct=True,
            )
        )
        .order_by(
            "start_time",
            "class_instance__name",
        )
    )

    rows = []

    for meeting in meetings[:12]:
        rows.append(
            {
                "meeting": meeting,
                "class": meeting.class_instance,
                "location": (
                    meeting.location
                    or meeting.class_instance.default_location
                ),
                "enrollment_count": meeting.enrollment_count,
            }
        )

    return rows


def _admin_week_schedule(studio, today):
    end_date = today + timedelta(days=6)

    events = (
        CalendarEvent.objects
        .filter(
            studio=studio,
            is_active=True,
            start_at__date__gte=today,
            start_at__date__lte=end_date,
        )
        .order_by("start_at")
    )

    rows_by_date = {
        today + timedelta(days=offset): []
        for offset in range(7)
    }

    for event in events:
        event_date = timezone.localtime(
            event.start_at
        ).date()

        rows_by_date.setdefault(
            event_date,
            [],
        ).append(
            {
                "kind": "event",
                "title": event.title,
                "time": timezone.localtime(
                    event.start_at
                ).time(),
                "location": event.location,
            }
        )

    meetings = (
        ClassMeeting.objects
        .filter(
            class_instance__studio=studio,
            class_instance__is_active=True,
            class_instance__season__start_date__lte=end_date,
            class_instance__season__end_date__gte=today,
            is_active=True,
        )
        .select_related(
            "class_instance",
            "class_instance__season",
            "location",
            "class_instance__default_location",
        )
        .order_by(
            "day_of_week",
            "start_time",
        )
    )

    for target_date in rows_by_date:
        weekday = target_date.weekday()

        for meeting in meetings:
            if meeting.day_of_week != weekday:
                continue

            season = meeting.class_instance.season

            if not (
                season.start_date
                <= target_date
                <= season.end_date
            ):
                continue

            location = (
                meeting.location
                or meeting.class_instance.default_location
            )

            rows_by_date[target_date].append(
                {
                    "kind": "class",
                    "title": meeting.class_instance.name,
                    "time": meeting.start_time,
                    "location": (
                        location.name
                        if location
                        else ""
                    ),
                }
            )

    days = []

    for target_date, items in rows_by_date.items():
        items.sort(
            key=lambda item: (
                item["time"],
                item["title"],
            )
        )

        days.append(
            {
                "date": target_date,
                "items": items[:6],
                "count": len(items),
            }
        )

    return days


def _admin_attendance_alerts(studio, today):
    since = today - timedelta(days=30)

    repeated_absences = (
        AttendanceRecord.objects
        .filter(
            session__class_instance__studio=studio,
            session__session_date__gte=since,
            status=AttendanceRecord.Status.ABSENT,
        )
        .values(
            "student_id",
            "student__first_name",
            "student__last_name",
        )
        .annotate(
            absence_count=Count("id"),
        )
        .filter(
            absence_count__gte=2,
        )
        .order_by(
            "-absence_count",
            "student__last_name",
            "student__first_name",
        )[:6]
    )

    class_alerts = []

    recent_sessions = (
        AttendanceSession.objects
        .filter(
            class_instance__studio=studio,
            session_date__gte=since,
        )
        .select_related(
            "class_instance",
        )
        .prefetch_related(
            "records",
        )
        .order_by(
            "class_instance_id",
            "-session_date",
        )
    )

    aggregate = {}

    for session in recent_sessions:
        bucket = aggregate.setdefault(
            session.class_instance_id,
            {
                "class": session.class_instance,
                "total": 0,
                "present_like": 0,
            },
        )

        for record in session.records.all():
            bucket["total"] += 1

            if record.status in {
                AttendanceRecord.Status.PRESENT,
                AttendanceRecord.Status.LATE,
                AttendanceRecord.Status.LEFT_EARLY,
            }:
                bucket["present_like"] += 1

    for bucket in aggregate.values():
        if bucket["total"] < 3:
            continue

        rate = round(
            (
                bucket["present_like"]
                / bucket["total"]
            )
            * 100
        )

        if rate < 80:
            class_alerts.append(
                {
                    "class": bucket["class"],
                    "rate": rate,
                    "records": bucket["total"],
                }
            )

    class_alerts.sort(
        key=lambda item: (
            item["rate"],
            item["class"].name,
        )
    )

    return {
        "students": list(repeated_absences),
        "classes": class_alerts[:5],
    }


def _admin_quick_links(layout, studio):
    selected = layout.get(
        "quick_links",
        [],
    )

    preset_map = {
        "calendar": {
            "label": "Calendar",
            "icon": "▣",
            "url": reverse(
                "scheduling:calendar",
                args=[studio.slug],
            ),
        },
        "classes": {
            "label": "Class Manager",
            "icon": "◇",
            "url": "/admin/classes/class/",
        },
        "students": {
            "label": "Students",
            "icon": "○",
            "url": "/admin/students/student/",
        },
        "instructors": {
            "label": "Instructors",
            "icon": "△",
            "url": "/admin/instructors/instructor/",
        },
        "announcements": {
            "label": "Announcements",
            "icon": "✦",
            "url": reverse(
                "communications:announcement_list",
                args=[studio.slug],
            ),
        },
        "tasks": {
            "label": "Tasks",
            "icon": "✓",
            "url": reverse(
                "tasks:task_list",
                args=[studio.slug],
            ),
        },
    }

    rows = [
        preset_map[key]
        for key in selected
        if key in preset_map
    ]

    for item in layout.get(
        "custom_quick_links",
        [],
    ):
        rows.append(
            {
                "label": item["label"],
                "icon": "↗",
                "url": item["url"],
            }
        )

    return rows[:8]

@login_required
def admin_dashboard(request, studio_slug):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    if request.user.is_superuser:
        membership_role = "administrator"
    else:
        membership = (
            request.user.studio_memberships
            .filter(
                studio=studio,
                is_active=True,
                role="administrator",
            )
            .first()
        )

        if membership is None:
            return render(
                request,
                "dashboard/access_denied.html",
                {"studio": studio},
                status=403,
            )

        membership_role = membership.role

    preference, _created = DashboardPreference.objects.get_or_create(
        user=request.user,
        studio=studio,
        dashboard_type=DashboardPreference.DashboardType.ADMIN,
        defaults={"layout": default_admin_dashboard_layout()},
    )

    admin_layout = normalize_admin_dashboard_layout(preference.layout)
    admin_dashboard_cards = admin_dashboard_render_cards(admin_layout)

    today = timezone.localdate()
    studio_snapshot = _admin_studio_snapshot(
        studio,
        today,
    )
    now = timezone.now()
    next_30_days = now + timedelta(days=30)

    active_students = Student.objects.filter(
        studio=studio,
        is_active=True,
    ).count()

    total_students = Student.objects.filter(
        studio=studio,
    ).count()

    active_instructors = Instructor.objects.filter(
        studio=studio,
        is_active=True,
    ).count()

    active_classes = (
        Class.objects
        .filter(
            studio=studio,
            is_active=True,
        )
        .select_related(
            "season",
            "class_type",
            "instructor",
        )
        .annotate(
            active_enrollment_count=Count(
                "enrollments",
                filter=Q(
                    enrollments__status=Enrollment.Status.ACTIVE,
                ),
                distinct=True,
            )
        )
    )

    active_class_count = active_classes.count()

    active_enrollment_count = Enrollment.objects.filter(
        class_instance__studio=studio,
        status=Enrollment.Status.ACTIVE,
    ).count()

    waitlist_count = Enrollment.objects.filter(
        class_instance__studio=studio,
        status=Enrollment.Status.WAITLISTED,
    ).count()

    classes_near_capacity = []

    for class_instance in active_classes:
        if class_instance.capacity <= 0:
            continue

        remaining = (
            class_instance.capacity
            - class_instance.active_enrollment_count
        )

        percent_full = (
            class_instance.active_enrollment_count
            / class_instance.capacity
        ) * 100

        if percent_full >= 80:
            classes_near_capacity.append(
                {
                    "class": class_instance,
                    "remaining": max(remaining, 0),
                    "percent_full": round(percent_full),
                }
            )

    classes_near_capacity.sort(
        key=lambda item: (
            -item["percent_full"],
            item["remaining"],
        )
    )

    upcoming_events = (
        CalendarEvent.objects
        .filter(
            studio=studio,
            is_active=True,
            start_at__gte=now,
            start_at__lte=next_30_days,
        )
        .select_related(
            "class_instance",
            "instructor",
        )
        .order_by("start_at")[:6]
    )

    recent_enrollments = (
        Enrollment.objects
        .filter(
            class_instance__studio=studio,
        )
        .select_related(
            "student",
            "class_instance",
        )
        .order_by("-created_at")[:8]
    )

    upcoming_birthdays = []

    for student in Student.objects.filter(
        studio=studio,
        is_active=True,
    ):
        birthday_this_year = student.birthday.replace(
            year=today.year,
        )

        if birthday_this_year < today:
            birthday_this_year = student.birthday.replace(
                year=today.year + 1,
            )

        days_until = (
            birthday_this_year - today
        ).days

        if days_until <= 30:
            upcoming_birthdays.append(
                {
                    "student": student,
                    "date": birthday_this_year,
                    "days_until": days_until,
                }
            )

    upcoming_birthdays.sort(
        key=lambda item: item["date"]
    )

    today_classes = _admin_today_classes(
        studio,
        today,
    )

    week_schedule = _admin_week_schedule(
        studio,
        today,
    )

    attendance_alerts = _admin_attendance_alerts(
        studio,
        today,
    )

    admin_tasks = (
        visible_tasks_for_user(
            request.user,
            studio,
            "administrator",
        )
        .filter(
            is_active=True,
            student__isnull=True,
        )
        .exclude(
            completions__user=request.user,
        )
        .select_related(
            "assigned_to",
            "class_instance",
        )
        .distinct()[:8]
    )

    admin_announcements = (
        Announcement.objects
        .filter(
            studio=studio,
            is_published=True,
            publish_at__lte=now,
        )
        .filter(
            Q(expires_at__isnull=True)
            | Q(expires_at__gt=now)
        )
        .order_by(
            "-is_pinned",
            "-publish_at",
            "-created_at",
        )[:6]
    )

    admin_quick_links = _admin_quick_links(
        admin_layout,
        studio,
    )

    return render(
        request,
        "dashboard/admin_dashboard.html",
        {
            "studio": studio,
            "role": membership_role,
            "active_students": active_students,
            "total_students": total_students,
            "active_instructors": active_instructors,
            "active_class_count": active_class_count,
            "active_enrollment_count": active_enrollment_count,
            "waitlist_count": waitlist_count,
            "classes_near_capacity": classes_near_capacity[:6],
            "upcoming_events": upcoming_events,
            "recent_enrollments": recent_enrollments,
            "upcoming_birthdays": upcoming_birthdays[:6],
            "today_classes": today_classes,
            "week_schedule": week_schedule,
            "attendance_alerts": attendance_alerts,
            "admin_tasks": admin_tasks,
            "admin_announcements": admin_announcements,
            "admin_quick_links": admin_quick_links,
            "studio_snapshot": studio_snapshot,
            "admin_dashboard_cards": admin_dashboard_cards,
        },
    )


@login_required
def teacher_dashboard(request, studio_slug):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    instructor = (
        Instructor.objects
        .filter(
            studio=studio,
            user=request.user,
            is_active=True,
        )
        .first()
    )

    if not instructor:
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    now = timezone.localtime()
    today = now.date()
    weekday = today.weekday()

    today_meetings = (
        ClassMeeting.objects
        .filter(
            class_instance__studio=studio,
            class_instance__is_active=True,
            class_instance__season__start_date__lte=today,
            class_instance__season__end_date__gte=today,
            day_of_week=weekday,
            is_active=True,
        )
        .filter(
            Q(class_instance__instructor=instructor)
            | Q(
                class_instance__assistant_instructor=instructor
            )
        )
        .select_related(
            "class_instance",
            "class_instance__season",
            "class_instance__class_type",
            "class_instance__instructor",
            "class_instance__assistant_instructor",
            "location",
            "class_instance__default_location",
        )
        .order_by(
            "start_time",
            "class_instance__name",
        )
    )

    today_class_cards = []

    for meeting in today_meetings:
        class_instance = meeting.class_instance

        start_at = timezone.make_aware(
            datetime.combine(
                today,
                meeting.start_time,
            ),
            timezone.get_current_timezone(),
        )

        end_at = start_at + timedelta(
            minutes=meeting.duration_minutes
        )

        if now < start_at:
            status = "upcoming"
            status_label = "Upcoming"
        elif start_at <= now < end_at:
            status = "in_progress"
            status_label = "In Progress"
        else:
            status = "completed"
            status_label = "Completed"

        if (
            class_instance.min_age is not None
            and class_instance.max_age is not None
        ):
            if (
                class_instance.min_age
                == class_instance.max_age
            ):
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
        else:
            age_label = ""

        location = (
            meeting.location
            or class_instance.default_location
        )

        student_count = (
            Enrollment.objects
            .filter(
                class_instance=class_instance,
                status=Enrollment.Status.ACTIVE,
            )
            .count()
        )

        today_class_cards.append(
            {
                "class": class_instance,
                "meeting": meeting,
                "start_at": start_at,
                "end_at": end_at,
                "status": status,
                "status_label": status_label,
                "age_label": age_label,
                "location": location,
                "student_count": student_count,
            }
        )

    default_selected_index = None

    teacher_classes = (
        Class.objects
        .filter(
            studio=studio,
            is_active=True,
        )
        .filter(
            Q(instructor=instructor)
            | Q(
                assistant_instructor=instructor
            )
        )
        .distinct()
    )

    teacher_class_ids = list(
        teacher_classes.values_list(
            "id",
            flat=True,
        )
    )

    teacher_dances = (
        ChoreographyPlan.objects
        .filter(
            studio=studio,
            class_instance_id__in=teacher_class_ids,
        )
        .select_related(
            "class_instance",
        )
        .order_by(
            "class_instance__name",
            "title",
            "id",
        )
    )

    dances_by_class = {}

    for dance in teacher_dances:
        dances_by_class.setdefault(
            dance.class_instance_id,
            [],
        ).append(dance)

    teacher_dance_groups = [
        {
            "class": class_instance,
            "dances": dances_by_class.get(
                class_instance.id,
                [],
            ),
        }
        for class_instance in teacher_classes.order_by(
            "name",
            "id",
        )
    ]

    upcoming_teacher_events = (
        CalendarEvent.objects
        .filter(
            studio=studio,
            is_active=True,
            start_at__gte=now,
        )
        .filter(
            Q(
                audience=CalendarEvent.Audience.STUDIO
            )
            | Q(
                audience=CalendarEvent.Audience.TEACHERS
            )
            | Q(
                audience=CalendarEvent.Audience.CLASS_MEMBERS,
                class_instance_id__in=teacher_class_ids,
            )
        )
        .select_related(
            "class_instance",
            "instructor",
        )
        .distinct()
        .order_by(
            "start_at",
        )[:5]
    )

    teacher_announcements = (
        Announcement.objects
        .filter(
            studio=studio,
            is_published=True,
            publish_at__lte=now,
        )
        .filter(
            Q(expires_at__isnull=True)
            | Q(expires_at__gt=now)
        )
        .filter(
            Q(
                audience__in=[
                    Announcement.Audience.STUDIO,
                    Announcement.Audience.STAFF,
                    Announcement.Audience.TEACHERS,
                ]
            )
            | Q(
                audience=Announcement.Audience.CLASS,
                classes__id__in=teacher_class_ids,
            )
        )
        .distinct()
        .order_by(
            "-is_pinned",
            "-publish_at",
            "-created_at",
        )[:4]
    )

    recent_extra_work = (
        ExtraWorkEntry.objects
        .filter(
            studio=studio,
            user=request.user,
        )
        .order_by(
            "-work_date",
            "-created_at",
        )[:4]
    )

    preference, _created = (
        DashboardPreference.objects
        .get_or_create(
            user=request.user,
            studio=studio,
            dashboard_type=(
                DashboardPreference
                .DashboardType
                .TEACHER
            ),
            defaults={
                "layout": (
                    default_teacher_dashboard_layout()
                ),
            },
        )
    )

    teacher_layout = (
        normalize_teacher_dashboard_layout(
            preference.layout
        )
    )

    teacher_dashboard_cards = (
        teacher_dashboard_render_cards(
            teacher_layout
        )
    )

    quick_actions = (
        teacher_layout.get(
            "quick_actions",
            {},
        )
    )

    return render(
        request,
        "dashboard/teacher_dashboard.html",
        {
            "studio": studio,
            "role": "teacher",
            "instructor": instructor,
            "today_class_cards": today_class_cards,
            "default_selected_index": (
                default_selected_index
            ),
            "today": today,
            "now": now,
            "upcoming_teacher_events": (
                upcoming_teacher_events
            ),
            "teacher_announcements": (
                teacher_announcements
            ),
            "recent_extra_work": (
                recent_extra_work
            ),
            "teacher_dance_groups": (
                teacher_dance_groups
            ),
            "teacher_tasks": (
                visible_tasks_for_user(
                    request.user,
                    studio,
                    "teacher",
                )
                .filter(
                    student__isnull=True,
                )
                .exclude(
                    completions__user=request.user,
                )
                .distinct()[:5]
            ),
            "teacher_dashboard_cards": (
                teacher_dashboard_cards
            ),
            "teacher_quick_actions": (
                quick_actions
            ),
            "dashboard_header": {
                "greeting": (
                    "Good morning"
                    if now.hour < 12
                    else (
                        "Good afternoon"
                        if now.hour < 17
                        else "Good evening"
                    )
                ),
                "name": instructor.first_name,
                "subtitle": (
                    f"Here's what's happening at "
                    f"{studio.name} today."
                ),
                "date": today,
            },
        },
    )


@login_required
def family_dashboard(request, studio_slug):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    # Respect the selected Family workspace. This prevents a multi-role
    # test account from accidentally acting as an administrator here.
    selected_role = _selected_workspace_role(
        request,
        studio,
    )

    if selected_role != "family":
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    guardian = (
        Guardian.objects
        .filter(
            family__studio=studio,
            user=request.user,
            is_active=True,
        )
        .select_related("family")
        .first()
    )

    if not guardian:
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    students = (
        guardian.family.students
        .filter(is_active=True)
        .order_by("first_name", "last_name")
    )

    family_active_enrollments = (
        Enrollment.objects
        .filter(
            student__family=guardian.family,
            student__is_active=True,
            status=Enrollment.Status.ACTIVE,
            class_instance__studio=studio,
            class_instance__is_active=True,
        )
        .select_related(
            "student",
            "class_instance",
            "class_instance__instructor",
            "class_instance__season",
        )
        .prefetch_related(
            "class_instance__meeting_times",
        )
        .order_by(
            "student__first_name",
            "class_instance__name",
        )
    )

    enrollment_map = {}

    for enrollment in family_active_enrollments:
        enrollment_map.setdefault(
            enrollment.student_id,
            [],
        ).append(enrollment)

    student_cards = []

    for student in students:
        active_enrollments = enrollment_map.get(
            student.id,
            [],
        )

        student_cards.append(
            {
                "student": student,
                "enrollments": active_enrollments,
                "class_count": len(active_enrollments),
                "attendance": _attendance_stats_for_student(
                    student
                ),
            }
        )

    upcoming_classes = _next_class_meetings(
        list(family_active_enrollments),
        limit=8,
        days_ahead=21,
    )

    enrolled_class_ids = list(
        family_active_enrollments.values_list(
            "class_instance_id",
            flat=True,
        )
    )

    # Families should see studio-wide events and class-member events only
    # for classes their students are actively enrolled in.
    upcoming_events = (
        CalendarEvent.objects
        .filter(
            studio=studio,
            is_active=True,
            start_at__gte=timezone.now(),
        )
        .filter(
            Q(audience=CalendarEvent.Audience.STUDIO)
            | Q(
                audience=CalendarEvent.Audience.CLASS_MEMBERS,
                class_instance_id__in=enrolled_class_ids,
            )
        )
        .select_related(
            "class_instance",
        )
        .order_by("start_at")[:5]
    )

    return render(
        request,
        "dashboard/family_dashboard.html",
        {
            "studio": studio,
            "role": "family",
            "guardian": guardian,
            "family": guardian.family,
            "student_cards": student_cards,
            "upcoming_classes": upcoming_classes,
            "upcoming_events": upcoming_events,
        },
    )


@login_required
def student_dashboard(request, studio_slug):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    student = (
        Student.objects
        .filter(
            studio=studio,
            user=request.user,
            is_active=True,
        )
        .first()
    )

    if not student:
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    active_enrollments = (
        Enrollment.objects
        .filter(
            student=student,
            status=Enrollment.Status.ACTIVE,
        )
        .select_related(
            "class_instance",
            "class_instance__instructor",
            "class_instance__season",
        )
    )

    recent_attendance = (
        AttendanceRecord.objects
        .filter(student=student)
        .select_related(
            "session",
            "session__class_instance",
        )
        .order_by(
            "-session__session_date"
        )[:6]
    )

    return render(
        request,
        "dashboard/student_dashboard.html",
        {
            "studio": studio,
            "role": "student",
            "student": student,
            "active_enrollments": active_enrollments,
            "attendance": _attendance_stats_for_student(
                student
            ),
            "recent_attendance": recent_attendance,
        },
    )
