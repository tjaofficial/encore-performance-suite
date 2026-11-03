from datetime import datetime, timedelta
from decimal import Decimal
import math

from .parent_portal import parent_portal_context
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Sum
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
from attendance.models import AttendanceRecord, AttendanceSession, MakeupAssignment
from billing.models import Charge, CreditAllocation, Payment, PaymentAllocation
from classes.models import Class, ClassMeeting
from communications.models import Announcement
from costumes.models import StudentCostumeAssignment
from enrollments.models import Enrollment
from families.models import Guardian
from instructors.models import Instructor
from performance.models import ChoreographyPlan
from scheduling.models import CalendarEvent
from students.models import Student
from studios.models import Studio
from tasks.models import TaskAssignment
from tasks.services import visible_tasks_for_user
from timekeeping.models import ExtraWorkEntry


def _attendance_stats_for_student(
    student,
    *,
    start_date=None,
    end_date=None,
):
    records = AttendanceRecord.objects.filter(
        student=student,
    )

    if start_date is not None:
        records = records.filter(
            session__session_date__gte=start_date,
        )

    if end_date is not None:
        records = records.filter(
            session__session_date__lte=end_date,
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



def _student_week_schedule(
    enrollments,
    *,
    week_start,
):
    week_end = week_start + timedelta(days=6)
    rows = []

    for enrollment in enrollments:
        class_instance = enrollment.class_instance
        season = class_instance.season

        for meeting in class_instance.meeting_times.filter(
            is_active=True,
        ).select_related("location"):
            # week_start is Sunday. ClassMeeting uses Python weekday
            # numbering where Monday=0 and Sunday=6.
            day_offset = (meeting.day_of_week + 1) % 7
            occurrence_date = week_start + timedelta(
                days=day_offset
            )

            if (
                occurrence_date < season.start_date
                or occurrence_date > season.end_date
                or occurrence_date > week_end
            ):
                continue

            start_at = timezone.make_aware(
                datetime.combine(
                    occurrence_date,
                    meeting.start_time,
                ),
                timezone.get_current_timezone(),
            )

            end_at = start_at + timedelta(
                minutes=meeting.duration_minutes or 0
            )

            rows.append(
                {
                    "date": occurrence_date,
                    "student": enrollment.student,
                    "class_instance": class_instance,
                    "meeting": meeting,
                    "start_at": start_at,
                    "end_at": end_at,
                }
            )

    rows.sort(
        key=lambda item: (
            item["date"],
            item["start_at"],
            item["class_instance"].name,
        )
    )
    return rows



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


def _month_start(value):
    return value.replace(day=1)


def _shift_month(value, offset):
    month_index = (value.year * 12) + (value.month - 1) + offset
    year, month_zero = divmod(month_index, 12)
    return value.replace(
        year=year,
        month=month_zero + 1,
        day=1,
    )


def _percent_change(current, previous):
    current_value = Decimal(current or 0)
    previous_value = Decimal(previous or 0)

    if previous_value == 0:
        if current_value == 0:
            return {
                "value": 0,
                "direction": "flat",
                "label": "No change",
            }

        return {
            "value": 100,
            "direction": "up",
            "label": "New this month",
        }

    value = round(
        ((current_value - previous_value) / previous_value) * 100
    )

    if value > 0:
        direction = "up"
        label = f"{abs(value)}% vs last month"
    elif value < 0:
        direction = "down"
        label = f"{abs(value)}% vs last month"
    else:
        direction = "flat"
        label = "No change vs last month"

    return {
        "value": value,
        "direction": direction,
        "label": label,
    }


def _nice_axis_max(value, *, intervals=4):
    """Return an axis ceiling that produces evenly spaced, human-friendly ticks."""
    value = float(value or 0)

    if value <= 0:
        return 0.0

    raw_step = value / intervals
    magnitude = 10 ** math.floor(math.log10(raw_step))
    normalized = raw_step / magnitude

    if normalized <= 1:
        nice_step = 1
    elif normalized <= 2:
        nice_step = 2
    elif normalized <= 2.5:
        nice_step = 2.5
    elif normalized <= 5:
        nice_step = 5
    else:
        nice_step = 10

    step = nice_step * magnitude
    return float(step * intervals)


def _format_money_axis(value):
    value = float(value or 0)

    if value >= 1_000_000:
        return f"${value / 1_000_000:.1f}M".replace(".0M", "M")

    if value >= 1_000:
        return f"${value / 1_000:.1f}K".replace(".0K", "K")

    if value == int(value):
        return f"${int(value):,}"

    return f"${value:,.2f}"


def _chart_geometry(values, *, width=100, height=40, padding=4):
    clean_values = [float(value or 0) for value in values]

    if not clean_values:
        return {
            "points": "",
            "area_points": "",
            "positions": [],
            "axis_max": 0,
        }

    max_value = max(clean_values)
    axis_max = _nice_axis_max(max_value)
    scale_max = axis_max or 1.0
    usable_height = height - (padding * 2)
    x_padding = 2.5
    usable_width = width - (x_padding * 2)

    if len(clean_values) == 1:
        x_positions = [width / 2]
    else:
        step = usable_width / (len(clean_values) - 1)
        x_positions = [x_padding + (index * step) for index in range(len(clean_values))]

    positions = []
    points = []

    for x_value, raw_value in zip(x_positions, clean_values):
        ratio = raw_value / scale_max
        y_value = (height - padding) - (ratio * usable_height)
        position = {
            "x": round(x_value, 2),
            "y": round(y_value, 2),
            "x_pct": round((x_value / width) * 100, 3),
            "y_pct": round((y_value / height) * 100, 3),
            "value": raw_value,
        }
        positions.append(position)
        points.append(f"{x_value:.2f},{y_value:.2f}")

    first_x = x_positions[0]
    last_x = x_positions[-1]
    baseline = height - padding
    area_points = (
        f"{first_x:.2f},{baseline:.2f} "
        + " ".join(points)
        + f" {last_x:.2f},{baseline:.2f}"
    )

    return {
        "points": " ".join(points),
        "area_points": area_points,
        "positions": positions,
        "axis_max": axis_max,
    }


def _admin_analytics(studio, today):
    current_month = _month_start(today)
    previous_month = _shift_month(current_month, -1)
    next_month = _shift_month(current_month, 1)

    successful_payments = Payment.objects.filter(
        account__studio=studio,
        status=Payment.Status.SUCCEEDED,
    )

    current_revenue = (
        successful_payments
        .filter(
            paid_at__date__gte=current_month,
            paid_at__date__lt=next_month,
        )
        .aggregate(total=Sum("amount"))["total"]
        or Decimal("0.00")
    )

    previous_revenue = (
        successful_payments
        .filter(
            paid_at__date__gte=previous_month,
            paid_at__date__lt=current_month,
        )
        .aggregate(total=Sum("amount"))["total"]
        or Decimal("0.00")
    )

    current_payment_count = successful_payments.filter(
        paid_at__date__gte=current_month,
        paid_at__date__lt=next_month,
    ).count()

    revenue_change = _percent_change(
        current_revenue,
        previous_revenue,
    )

    revenue_rows = []
    enrollment_rows = []

    for offset in range(-5, 1):
        start = _shift_month(current_month, offset)
        end = _shift_month(start, 1)

        revenue_total = (
            successful_payments
            .filter(
                paid_at__date__gte=start,
                paid_at__date__lt=end,
            )
            .aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )

        enrollment_total = Enrollment.objects.filter(
            class_instance__studio=studio,
            created_at__date__gte=start,
            created_at__date__lt=end,
        ).count()

        revenue_rows.append(
            {
                "label": start.strftime("%b"),
                "value": revenue_total,
            }
        )
        enrollment_rows.append(
            {
                "label": start.strftime("%b"),
                "value": enrollment_total,
            }
        )

    revenue_geometry = _chart_geometry(
        [item["value"] for item in revenue_rows]
    )
    enrollment_geometry = _chart_geometry(
        [item["value"] for item in enrollment_rows]
    )

    for row, position in zip(revenue_rows, revenue_geometry["positions"]):
        row["x"] = position["x"]
        row["y"] = position["y"]
        row["x_pct"] = position["x_pct"]
        row["y_pct"] = position["y_pct"]
        row["display_value"] = f"${Decimal(row['value']):,.2f}"

    for row, position in zip(enrollment_rows, enrollment_geometry["positions"]):
        row["x"] = position["x"]
        row["y"] = position["y"]
        row["x_pct"] = position["x_pct"]
        row["y_pct"] = position["y_pct"]
        row["display_value"] = str(row["value"])

    revenue_axis_max = revenue_geometry["axis_max"]
    enrollment_axis_max = enrollment_geometry["axis_max"]

    revenue_y_ticks = [
        {
            "value": revenue_axis_max * fraction,
            "label": _format_money_axis(revenue_axis_max * fraction),
        }
        for fraction in (1, 0.75, 0.5, 0.25, 0)
    ]
    enrollment_y_ticks = [
        {
            "value": enrollment_axis_max * fraction,
            "label": (
                str(int(enrollment_axis_max * fraction))
                if float(enrollment_axis_max * fraction).is_integer()
                else f"{enrollment_axis_max * fraction:g}"
            ),
        }
        for fraction in (1, 0.75, 0.5, 0.25, 0)
    ]

    current_enrollments = enrollment_rows[-1]["value"] if enrollment_rows else 0
    previous_enrollments = enrollment_rows[-2]["value"] if len(enrollment_rows) > 1 else 0
    enrollment_change = _percent_change(
        current_enrollments,
        previous_enrollments,
    )

    attendance_start = today - timedelta(days=29)
    attendance_records = AttendanceRecord.objects.filter(
        session__class_instance__studio=studio,
        session__session_date__gte=attendance_start,
        session__session_date__lte=today,
    )

    attendance_total = attendance_records.count()
    attendance_present = attendance_records.filter(
        status__in=[
            AttendanceRecord.Status.PRESENT,
            AttendanceRecord.Status.LATE,
            AttendanceRecord.Status.LEFT_EARLY,
        ]
    ).count()
    attendance_absent = attendance_records.filter(
        status=AttendanceRecord.Status.ABSENT,
    ).count()
    attendance_excused = attendance_records.filter(
        status=AttendanceRecord.Status.EXCUSED,
    ).count()
    attendance_rate = (
        round((attendance_present / attendance_total) * 100)
        if attendance_total
        else 0
    )

    open_charges = list(
        Charge.objects
        .filter(
            account__studio=studio,
            status__in=[
                Charge.Status.OPEN,
                Charge.Status.PARTIALLY_PAID,
            ],
        )
        .values(
            "id",
            "amount",
            "due_date",
            "account_id",
        )
    )

    charge_ids = [item["id"] for item in open_charges]

    payment_allocations = {
        row["charge_id"]: row["total"] or Decimal("0.00")
        for row in (
            PaymentAllocation.objects
            .filter(charge_id__in=charge_ids)
            .values("charge_id")
            .annotate(total=Sum("amount"))
        )
    }
    credit_allocations = {
        row["charge_id"]: row["total"] or Decimal("0.00")
        for row in (
            CreditAllocation.objects
            .filter(charge_id__in=charge_ids)
            .values("charge_id")
            .annotate(total=Sum("amount"))
        )
    }

    outstanding_total = Decimal("0.00")
    overdue_total = Decimal("0.00")
    outstanding_accounts = set()

    for charge in open_charges:
        remaining = max(
            Decimal(charge["amount"] or 0)
            - payment_allocations.get(charge["id"], Decimal("0.00"))
            - credit_allocations.get(charge["id"], Decimal("0.00")),
            Decimal("0.00"),
        )

        if remaining <= 0:
            continue

        outstanding_total += remaining
        outstanding_accounts.add(charge["account_id"])

        if charge["due_date"] and charge["due_date"] < today:
            overdue_total += remaining

    overdue_percent = (
        round(float(overdue_total / outstanding_total) * 100)
        if outstanding_total > 0
        else 0
    )

    source_start = today - timedelta(days=89)
    source_field = Enrollment._meta.get_field("source")
    source_labels = dict(source_field.flatchoices)
    source_rows_raw = list(
        Enrollment.objects
        .filter(
            class_instance__studio=studio,
            created_at__date__gte=source_start,
            created_at__date__lte=today,
        )
        .values("source")
        .annotate(total=Count("id"))
        .order_by("-total", "source")[:5]
    )
    source_max = max(
        [row["total"] for row in source_rows_raw],
        default=0,
    )
    source_rows = [
        {
            "key": row["source"],
            "label": source_labels.get(
                row["source"],
                str(row["source"] or "Unknown").replace("_", " ").title(),
            ),
            "total": row["total"],
            "percent": (
                round((row["total"] / source_max) * 100)
                if source_max
                else 0
            ),
        }
        for row in source_rows_raw
    ]

    return {
        "monthly_revenue": {
            "total": current_revenue,
            "previous_total": previous_revenue,
            "payment_count": current_payment_count,
            "change": revenue_change,
        },
        "revenue_trend": {
            "rows": revenue_rows,
            "points": revenue_geometry["points"],
            "area_points": revenue_geometry["area_points"],
            "y_ticks": revenue_y_ticks,
            "current_total": current_revenue,
            "change": revenue_change,
        },
        "enrollment_trend": {
            "rows": enrollment_rows,
            "points": enrollment_geometry["points"],
            "area_points": enrollment_geometry["area_points"],
            "y_ticks": enrollment_y_ticks,
            "current_total": current_enrollments,
            "change": enrollment_change,
        },
        "attendance_rate": {
            "rate": attendance_rate,
            "total": attendance_total,
            "present": attendance_present,
            "absent": attendance_absent,
            "excused": attendance_excused,
        },
        "outstanding_balances": {
            "total": outstanding_total,
            "overdue": overdue_total,
            "overdue_percent": overdue_percent,
            "family_count": len(outstanding_accounts),
        },
        "registration_sources": {
            "rows": source_rows,
            "days": 90,
        },
    }


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
    admin_analytics = _admin_analytics(
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
            "admin_analytics": admin_analytics,
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

        def age_number(value):
            if value is None:
                return ""
            return str(int(value)) if value == int(value) else str(value).rstrip("0").rstrip(".")

        if class_instance.min_age is not None:
            age_label = age_label.replace(str(class_instance.min_age), age_number(class_instance.min_age))
        if class_instance.max_age is not None:
            age_label = age_label.replace(str(class_instance.max_age), age_number(class_instance.max_age))

        location = (
            meeting.location
            or class_instance.default_location
        )

        roster_enrollments = list(
            Enrollment.objects.filter(
                class_instance=class_instance,
                status=Enrollment.Status.ACTIVE,
                student__studio=studio,
            ).select_related("student").order_by(
                "student__last_name", "student__first_name", "pk"
            )
        )
        roster = [{"student": enrollment.student} for enrollment in roster_enrollments]
        student_count = len(roster)

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
                "roster": roster,
                "present_like_count": 0,
            }
        )

    default_selected_index = -1

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

    # Resolve active meeting days/times so similarly named dance classes
    # remain distinguishable on the teacher dashboard.
    teacher_dance_groups = []
    for class_instance in teacher_classes.prefetch_related("meeting_times").order_by("name", "id"):
        meetings = [m for m in class_instance.meeting_times.all() if m.is_active]
        meetings.sort(key=lambda m: (m.day_of_week, m.start_time))
        meeting_label = ", ".join(
            f"{m.get_day_of_week_display()} {m.start_time.strftime('%I:%M %p').lstrip('0')}"
            for m in meetings
        ) or "Schedule not set"
        teacher_dance_groups.append({
            "class": class_instance,
            "dances": dances_by_class.get(class_instance.id, []),
            "meeting_label": meeting_label,
        })

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

    # Teacher attendance is based on records in the instructor's classes,
    # not the instructor's own attendance or all studio attendance.
    attendance_qs = AttendanceRecord.objects.filter(
        session__class_instance_id__in=teacher_class_ids,
        session__session_date__lte=today,
        session__session_date__gte=today - timedelta(days=60),
    )
    attendance_total = attendance_qs.count()
    attendance_present = attendance_qs.filter(
        status__in=[
            AttendanceRecord.Status.PRESENT,
            AttendanceRecord.Status.LATE,
            AttendanceRecord.Status.LEFT_EARLY,
        ]
    ).count()
    teacher_attendance_percent = (
        round(100 * attendance_present / attendance_total)
        if attendance_total else None
    )
    teacher_recent_absences = (
        attendance_qs.filter(status=AttendanceRecord.Status.ABSENT)
        .select_related("student", "session", "session__class_instance")
        .order_by("-session__session_date", "-pk")[:8]
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

    # Restore Extra Work for older saved layouts where the card was omitted.
    if not any(card["key"] == "extra_work" for card in teacher_dashboard_cards):
        teacher_dashboard_cards.append({"key": "extra_work", "width": "quarter", "height": 2})

    # Include the new attendance card until older saved layouts can be
    # upgraded through the teacher layout registry.
    if not any(card["key"] == "attendance" for card in teacher_dashboard_cards):
        teacher_dashboard_cards.append({"key": "attendance", "width": "half", "height": 2})

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
            "teacher_attendance_percent": teacher_attendance_percent,
            "teacher_attendance_total": attendance_total,
            "teacher_attendance_present": attendance_present,
            "teacher_recent_absences": teacher_recent_absences,
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

    portal = parent_portal_context(
        request,
        studio,
        section="dashboard",
    )

    guardian = portal.get("guardian")
    family = portal.get("family")
    selected_student = portal.get("selected_student")

    if guardian is None or family is None:
        return render(
            request,
            "dashboard/access_denied.html",
            {"studio": studio},
            status=403,
        )

    family_active_enrollments = list(
        Enrollment.objects
        .filter(
            student__family=family,
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
            "class_instance__level",
            "class_instance__default_location",
        )
        .prefetch_related(
            "class_instance__meeting_times",
            "class_instance__meeting_times__location",
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

    selected_enrollments = (
        enrollment_map.get(
            selected_student.pk,
            [],
        )
        if selected_student is not None
        else []
    )

    today = timezone.localdate()
    base_week_start = today - timedelta(
        days=(today.weekday() + 1) % 7
    )

    try:
        week_offset = int(
            request.GET.get("week", "0") or 0
        )
    except (TypeError, ValueError):
        week_offset = 0

    week_offset = max(-52, min(52, week_offset))
    week_start = base_week_start + timedelta(
        days=(week_offset * 7)
    )
    week_end = week_start + timedelta(days=6)

    requested_date = str(
        request.GET.get("date", "") or ""
    ).strip()

    selected_date = None
    if requested_date:
        try:
            candidate = datetime.strptime(
                requested_date,
                "%Y-%m-%d",
            ).date()
        except (TypeError, ValueError):
            candidate = None

        if (
            candidate is not None
            and week_start <= candidate <= week_end
        ):
            selected_date = candidate

    if selected_date is None:
        selected_date = (
            today
            if week_offset == 0
            else week_start
            + timedelta(
                days=(today - base_week_start).days
            )
        )

    week_days = []
    for offset in range(7):
        value = week_start + timedelta(days=offset)
        week_days.append(
            {
                "date": value,
                "is_today": value == today,
                "is_selected": value == selected_date,
            }
        )

    week_schedule = _student_week_schedule(
        selected_enrollments,
        week_start=week_start,
    )

    selected_day_schedule = [
        item
        for item in week_schedule
        if item["date"] == selected_date
    ]

    next_class_rows = _next_class_meetings(
        selected_enrollments,
        limit=1,
        days_ahead=45,
    )
    next_class = (
        next_class_rows[0]
        if next_class_rows
        else None
    )

    # Scheduled make-ups are one-time visits, NOT class enrollments.
    makeup_bookings = list(
        MakeupAssignment.objects.filter(
            student=selected_student,
            status=MakeupAssignment.Status.SCHEDULED,
            scheduled_date__gte=min(week_start, today),
            scheduled_date__lte=max(week_end, today + timedelta(days=45)),
        ).select_related(
            "makeup_class", "makeup_class__season", "makeup_class__instructor",
            "makeup_meeting", "makeup_meeting__location",
        ) if selected_student is not None else []
    )
    for booking in makeup_bookings:
        meeting = booking.makeup_meeting
        if meeting is None or not meeting.is_active or not booking.makeup_class.is_active:
            continue
        start_at = timezone.make_aware(
            datetime.combine(booking.scheduled_date, meeting.start_time),
            timezone.get_current_timezone(),
        )
        end_at = start_at + timedelta(minutes=meeting.duration_minutes or 0)
        item = {
            "date": booking.scheduled_date,
            "student": selected_student,
            "class_instance": booking.makeup_class,
            "meeting": meeting,
            "start_at": start_at,
            "end_at": end_at,
            "is_makeup": True,
        }
        if week_start <= booking.scheduled_date <= week_end:
            week_schedule.append(item)
        if start_at >= timezone.now() and (next_class is None or start_at < next_class["start_at"]):
            next_class = item
    week_schedule.sort(key=lambda item: (item["date"], item["start_at"], item["class_instance"].name))
    selected_day_schedule = [item for item in week_schedule if item["date"] == selected_date]

    month_start = today.replace(day=1)
    attendance = (
        _attendance_stats_for_student(
            selected_student,
            start_date=month_start,
            end_date=today,
        )
        if selected_student is not None
        else {
            "total": 0,
            "present_like": 0,
            "absent": 0,
            "excused": 0,
            "percentage": None,
        }
    )

    selected_level = None
    for enrollment in selected_enrollments:
        if enrollment.class_instance.level_id:
            selected_level = enrollment.class_instance.level
            break

    selected_class_ids = [
        enrollment.class_instance_id
        for enrollment in selected_enrollments
    ]

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
                class_instance_id__in=selected_class_ids,
            )
        )
        .select_related(
            "class_instance",
        )
        .order_by("start_at")[:3]
    )

    announcements = (
        Announcement.objects
        .filter(
            studio=studio,
            is_published=True,
            publish_at__lte=timezone.now(),
        )
        .filter(
            Q(expires_at__isnull=True)
            | Q(expires_at__gt=timezone.now())
        )
        .filter(
            Q(
                audience__in=[
                    Announcement.Audience.STUDIO,
                    Announcement.Audience.FAMILIES,
                ]
            )
            | Q(
                audience=Announcement.Audience.CLASS,
                classes__id__in=selected_class_ids,
            )
        )
        .distinct()
        .order_by(
            "-is_pinned",
            "-publish_at",
            "-created_at",
        )[:3]
    )

    try:
        billing_account = family.billing_account
    except Exception:
        billing_account = None

    costume_snapshot = []
    if selected_student is not None:
        costume_snapshot = list(
            StudentCostumeAssignment.objects
            .filter(
                student=selected_student,
                is_active=True,
                costume__is_active=True,
            )
            .select_related(
                "costume",
                "costume__dance",
                "costume__dance__class_instance",
            )
            .prefetch_related("costume__images")
            .order_by(
                "costume__dance__title",
                "costume__name",
            )[:3]
        )

    latest_payment = None
    next_due_charge = None

    if billing_account is not None:
        latest_payment = (
            billing_account.payments
            .filter(status="succeeded")
            .order_by("-paid_at")
            .first()
        )

        next_due_charge = (
            billing_account.charges
            .filter(
                status__in=[
                    "open",
                    "partially_paid",
                ],
            )
            .order_by(
                "due_date",
                "created_at",
            )
            .first()
        )

    parent_task_rows = []

    if selected_student is not None:
        visible_parent_tasks = (
            visible_tasks_for_user(
                request.user,
                studio,
                "family",
            )
            .filter(
                is_student_facing=True,
                assignments__recipient_type=(
                    TaskAssignment.RecipientType.STUDENT
                ),
                assignments__student=selected_student,
            )
            .distinct()
        )

        for task in visible_parent_tasks:
            assignment = (
                task.assignments
                .filter(
                    recipient_type=(
                        TaskAssignment.RecipientType.STUDENT
                    ),
                    student=selected_student,
                )
                .first()
            )

            if (
                assignment is not None
                and assignment.completed_at is None
            ):
                parent_task_rows.append(
                    {
                        "task": task,
                        "assignment": assignment,
                        "system_managed": (task.description or "").startswith("[Encore make-up tracker:"),
                    }
                )

            if len(parent_task_rows) >= 6:
                break

    context = {
        **portal,
        "studio": studio,
        "role": "family",
        "selected_enrollments": selected_enrollments,
        "selected_level": selected_level,
        "next_class": next_class,
        "week_offset": week_offset,
        "prev_week_offset": week_offset - 1,
        "next_week_offset": week_offset + 1,
        "week_start": week_start,
        "week_end": week_end,
        "week_days": week_days,
        "selected_date": selected_date,
        "selected_day_schedule": selected_day_schedule,
        "attendance": attendance,
        "upcoming_events": upcoming_events,
        "announcements": announcements,
        "billing_account": billing_account,
        "latest_payment": latest_payment,
        "next_due_charge": next_due_charge,
        "costume_snapshot": costume_snapshot,
        "parent_task_rows": parent_task_rows,
        "today": today,
    }

    return render(
        request,
        "dashboard/family_dashboard.html",
        context,
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
