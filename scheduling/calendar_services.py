from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from attendance.models import AttendanceRecord
from classes.models import Class
from instructors.models import Instructor
from tasks.models import Task, TaskAssignment, TaskNotification
from tasks.services import visible_tasks_for_user

from .models import (
    CalendarCategory,
    CalendarEvent,
    CalendarPreference,
    CalendarRecurrence,
    ClassOccurrenceOverride,
    TeacherTimeOffDate,
    TeacherTimeOffRequest,
)


@dataclass
class CalendarOccurrence:
    start_at: datetime
    end_at: datetime


DEFAULT_MAIN_CATEGORIES = [
    ("Recital", "#2E3CF1"),
    ("Performance", "#0E169D"),
    ("Rehearsal", "#0197FC"),
    ("Fundraiser", "#7A5AF8"),
    ("Studio Event", "#1663FF"),
    ("Studio Closed", "#CF6685"),
]


def ensure_default_main_categories(studio):
    for sort_order, (name, color) in enumerate(
        DEFAULT_MAIN_CATEGORIES,
        start=1,
    ):
        CalendarCategory.objects.get_or_create(
            studio=studio,
            scope=CalendarCategory.Scope.MAIN,
            owner=None,
            name=name,
            defaults={
                "color": color,
                "is_public": True,
                "is_active": True,
                "sort_order": sort_order,
            },
        )


def get_calendar_preference(
    user,
    studio,
):
    preference, _ = CalendarPreference.objects.get_or_create(
        user=user,
        studio=studio,
    )
    return preference


def visible_calendar_events(
    user,
    studio,
    role,
):
    qs = (
        CalendarEvent.objects
        .filter(
            studio=studio,
            is_active=True,
        )
        .select_related(
            "category",
            "owner",
            "created_by",
        )
    )

    if role == "administrator":
        return qs.filter(
            Q(scope=CalendarEvent.Scope.MAIN)
            | Q(
                scope=CalendarEvent.Scope.PERSONAL,
                owner=user,
            )
        )

    if role == "teacher":
        return qs.filter(
            Q(scope=CalendarEvent.Scope.MAIN)
            | Q(
                scope=CalendarEvent.Scope.PERSONAL,
                owner=user,
            )
        )

    if role in {
        "family",
        "student",
    }:
        return qs.filter(
            scope=CalendarEvent.Scope.MAIN,
            audience=CalendarEvent.Audience.STUDIO,
        )

    return qs.none()


def visible_classes_for_role(
    user,
    studio,
    role,
    base_visible_classes,
):
    """
    Keep the existing scheduling service as the source of truth for which
    classes a user may see. This helper only adds deterministic ordering.
    """
    return (
        base_visible_classes
        .select_related(
            "instructor",
            "assistant_instructor",
            "season",
        )
        .prefetch_related(
            "meeting_times",
        )
        .order_by(
            "name",
        )
    )


def task_calendar_items(
    user,
    studio,
    role,
    start_date,
    end_date,
    *,
    include_completed=False,
):
    tasks = (
        visible_tasks_for_user(
            user,
            studio,
            role,
        )
        .filter(
            due_date__isnull=False,
            due_date__gte=start_date,
            due_date__lte=end_date,
        )
        .select_related(
            "class_instance",
            "student",
        )
        .prefetch_related(
            "assignments",
        )
        .distinct()
    )

    rows = []

    for task in tasks:
        assignment = None

        if role in {
            "administrator",
            "teacher",
        }:
            assignment = (
                task.assignments
                .filter(
                    recipient_type=TaskAssignment.RecipientType.USER,
                    user=user,
                )
                .first()
            )

        elif role == "student":
            student = getattr(
                user,
                "student_profile",
                None,
            )
            if student:
                assignment = (
                    task.assignments
                    .filter(
                        recipient_type=TaskAssignment.RecipientType.STUDENT,
                        student=student,
                    )
                    .first()
                )

        elif role == "family":
            assignment = (
                task.assignments
                .filter(
                    recipient_type=TaskAssignment.RecipientType.STUDENT,
                    student__family__guardians__user=user,
                    student__family__guardians__is_active=True,
                )
                .first()
            )

        completed = bool(
            assignment
            and assignment.completed_at
        )

        if completed and not include_completed:
            continue

        rows.append(
            {
                "id": f"task-{task.pk}",
                "title": task.title,
                "start": task.due_date.isoformat(),
                "allDay": True,
                "display": "block",
                "backgroundColor": (
                    "#8A93A8"
                    if completed
                    else "#1663FF"
                ),
                "borderColor": (
                    "#8A93A8"
                    if completed
                    else "#1663FF"
                ),
                "extendedProps": {
                    "sourceType": "task",
                    "sourceGroup": "tasks",
                    "taskId": task.pk,
                    "eventType": "Task",
                    "description": task.description,
                    "completed": completed,
                    "priority": task.priority,
                    "className": (
                        task.class_instance.name
                        if task.class_instance_id
                        else ""
                    ),
                    "editable": False,
                    "deletable": False,
                },
            }
        )

    return rows


def absence_calendar_items(
    user,
    studio,
    role,
    start_date,
    end_date,
):
    if role not in {
        "administrator",
        "teacher",
    }:
        return []

    records = (
        AttendanceRecord.objects
        .filter(
            session__class_instance__studio=studio,
            session__session_date__gte=start_date,
            session__session_date__lte=end_date,
            status__in=[
                AttendanceRecord.Status.ABSENT,
                AttendanceRecord.Status.EXCUSED,
            ],
        )
        .select_related(
            "student",
            "session",
            "session__class_instance",
            "session__class_instance__instructor",
            "session__class_instance__assistant_instructor",
        )
    )

    if role == "teacher":
        records = records.filter(
            Q(
                session__class_instance__instructor__user=user
            )
            | Q(
                session__class_instance__assistant_instructor__user=user
            )
        ).distinct()

    return [
        {
            "id": f"absence-{record.pk}",
            "title": (
                f"{record.student.first_name} "
                f"{record.student.last_name} · "
                f"{record.get_status_display()}"
            ),
            "start": record.session.session_date.isoformat(),
            "allDay": True,
            "backgroundColor": "#CF6685",
            "borderColor": "#CF6685",
            "extendedProps": {
                "sourceType": "absence",
                "sourceGroup": "absences",
                "eventType": "Absence",
                "student": str(record.student),
                "className": record.session.class_instance.name,
                "description": record.note,
                "editable": False,
                "deletable": False,
            },
        }
        for record in records
    ]


def _month_difference(
    start_date,
    candidate,
):
    return (
        (
            candidate.year
            - start_date.year
        )
        * 12
        + candidate.month
        - start_date.month
    )


def _year_difference(
    start_date,
    candidate,
):
    return candidate.year - start_date.year


def _matches_recurrence(
    recurrence,
    original_date,
    candidate,
):
    delta_days = (
        candidate
        - original_date
    ).days

    if delta_days < 0:
        return False

    if recurrence.frequency == CalendarRecurrence.Frequency.DAILY:
        return (
            delta_days
            % recurrence.interval
            == 0
        )

    if recurrence.frequency == CalendarRecurrence.Frequency.WEEKLY:
        week_delta = delta_days // 7

        if (
            week_delta
            % recurrence.interval
            != 0
        ):
            return False

        weekdays = (
            recurrence.weekdays
            or [
                original_date.weekday()
            ]
        )

        return (
            candidate.weekday()
            in weekdays
        )

    if recurrence.frequency == CalendarRecurrence.Frequency.MONTHLY:
        month_delta = _month_difference(
            original_date,
            candidate,
        )

        return (
            month_delta >= 0
            and month_delta
            % recurrence.interval
            == 0
            and candidate.day
            == original_date.day
        )

    if recurrence.frequency == CalendarRecurrence.Frequency.YEARLY:
        year_delta = _year_difference(
            original_date,
            candidate,
        )

        return (
            year_delta >= 0
            and year_delta
            % recurrence.interval
            == 0
            and candidate.month
            == original_date.month
            and candidate.day
            == original_date.day
        )

    return False


def expand_calendar_event(
    event,
    range_start,
    range_end,
):
    try:
        recurrence = event.recurrence
    except CalendarRecurrence.DoesNotExist:
        return [
            CalendarOccurrence(
                start_at=event.start_at,
                end_at=event.end_at,
            )
        ] if (
            event.start_at.date() <= range_end
            and event.end_at.date() >= range_start
        ) else []

    original_start = timezone.localtime(
        event.start_at
    )
    original_end = timezone.localtime(
        event.end_at
    )

    duration = (
        original_end
        - original_start
    )

    candidate = max(
        range_start,
        original_start.date(),
    )

    emitted = 0
    occurrence_number = 0
    max_scan_end = range_end

    if (
        recurrence.end_type
        == CalendarRecurrence.EndType.ON_DATE
        and recurrence.end_date
    ):
        max_scan_end = min(
            max_scan_end,
            recurrence.end_date,
        )

    rows = []

    scan = original_start.date()

    # Count from the original start so AFTER_COUNT remains stable even when
    # FullCalendar asks for a later window.
    while scan <= max_scan_end:
        if _matches_recurrence(
            recurrence,
            original_start.date(),
            scan,
        ):
            occurrence_number += 1

            if (
                recurrence.end_type
                == CalendarRecurrence.EndType.AFTER_COUNT
                and recurrence.occurrence_count
                and occurrence_number
                > recurrence.occurrence_count
            ):
                break

            if scan >= range_start:
                start_at = timezone.make_aware(
                    datetime.combine(
                        scan,
                        original_start.time().replace(
                            tzinfo=None,
                        ),
                    ),
                    timezone.get_current_timezone(),
                )

                rows.append(
                    CalendarOccurrence(
                        start_at=start_at,
                        end_at=start_at + duration,
                    )
                )
                emitted += 1

        scan += timedelta(days=1)

    return rows


def category_color(
    event,
):
    if event.color:
        return event.color

    if event.category_id:
        return event.category.color

    if event.scope == CalendarEvent.Scope.PERSONAL:
        return "#0197FC"

    return "#2E3CF1"


def event_json(
    event,
    occurrence,
    *,
    role,
    user,
):
    can_edit = (
        (
            event.scope
            == CalendarEvent.Scope.MAIN
            and role == "administrator"
        )
        or (
            event.scope
            == CalendarEvent.Scope.PERSONAL
            and event.owner_id == user.id
        )
    )

    color = category_color(
        event
    )

    occurrence_key = (
        occurrence.start_at.isoformat()
    )

    return {
        "id": (
            f"event-{event.pk}-"
            f"{occurrence_key}"
        ),
        "groupId": f"calendar-event-{event.pk}",
        "title": event.title,
        "start": occurrence.start_at.isoformat(),
        "end": occurrence.end_at.isoformat(),
        "allDay": event.all_day,
        "backgroundColor": color,
        "borderColor": color,
        "extendedProps": {
            "sourceType": "calendar_event",
            "sourceGroup": (
                "personal"
                if event.scope
                == CalendarEvent.Scope.PERSONAL
                else "main"
            ),
            "calendarEventId": event.pk,
            "scope": event.scope,
            "eventType": event.get_event_type_display(),
            "categoryId": event.category_id,
            "categoryName": (
                event.category.name
                if event.category_id
                else ""
            ),
            "description": event.description,
            "location": event.location,
            "notes": event.notes,
            "isPublic": event.is_public,
            "editable": can_edit,
            "deletable": can_edit,
            "recurring": hasattr(event, "recurrence"),
        },
    }


User = get_user_model()


def admin_users_for_studio(studio):
    return (
        User.objects
        .filter(
            studio_memberships__studio=studio,
            studio_memberships__role="administrator",
            studio_memberships__is_active=True,
            is_active=True,
        )
        .distinct()
    )


def create_time_off_admin_task(
    time_off_request,
    *,
    creator,
):
    first_date = (
        time_off_request.dates
        .order_by(
            "date"
        )
        .values_list(
            "date",
            flat=True,
        )
        .first()
    )

    task = Task.objects.create(
        studio=time_off_request.studio,
        title=(
            "Review Time Off Request · "
            f"{time_off_request.instructor.full_name}"
        ),
        description=(
            f"Review {time_off_request.instructor.full_name}'s "
            f"time off request: {time_off_request.reason}"
        ),
        priority=Task.Priority.HIGH,
        due_date=first_date,
        created_by=None,
        context_type=Task.ContextType.ADMIN,
        audience_type=Task.AudienceType.ADMIN,
        approval_status=Task.ApprovalStatus.APPROVED,
        notify_assignees=True,
    )

    for admin in admin_users_for_studio(
        time_off_request.studio
    ):
        TaskAssignment.objects.get_or_create(
            task=task,
            recipient_type=TaskAssignment.RecipientType.USER,
            user=admin,
        )

        TaskNotification.objects.create(
            studio=time_off_request.studio,
            user=admin,
            task=task,
            kind=TaskNotification.Kind.APPROVAL,
            title="New Time Off Request",
            message=(
                f"{time_off_request.instructor.full_name} "
                "submitted a time off request."
            ),
        )

    time_off_request.admin_task = task
    time_off_request.save(
        update_fields=[
            "admin_task",
            "updated_at",
        ]
    )

    return task


def affected_occurrences_for_time_off_date(
    time_off_date,
):
    instructor = (
        time_off_date.request.instructor
    )

    request_date = (
        time_off_date.date
    )

    classes = (
        Class.objects
        .filter(
            studio=time_off_date.request.studio,
            is_active=True,
            season__start_date__lte=request_date,
            season__end_date__gte=request_date,
        )
        .filter(
            Q(instructor=instructor)
            | Q(
                assistant_instructor=instructor
            )
        )
        .select_related(
            "season",
            "instructor",
            "assistant_instructor",
        )
        .prefetch_related(
            "meeting_times",
        )
        .distinct()
    )

    rows = []

    for class_instance in classes:
        meetings = (
            class_instance.meeting_times
            .filter(
                is_active=True,
                day_of_week=request_date.weekday(),
            )
            .select_related(
                "room",
                "location",
            )
        )

        for meeting in meetings:
            existing_override = (
                ClassOccurrenceOverride.objects
                .filter(
                    class_instance=class_instance,
                    meeting=meeting,
                    occurrence_date=request_date,
                    absent_instructor=instructor,
                    status=ClassOccurrenceOverride.Status.ACTIVE,
                )
                .select_related(
                    "substitute_instructor",
                )
                .first()
            )

            rows.append(
                {
                    "time_off_date": time_off_date,
                    "class_instance": class_instance,
                    "meeting": meeting,
                    "absent_instructor": instructor,
                    "existing_override": existing_override,
                }
            )

    return rows


def approved_occurrences_needing_coverage(
    time_off_request,
):
    rows = []

    for date_record in (
        time_off_request.dates
        .filter(
            status=TeacherTimeOffDate.Status.COVERAGE_REQUIRED,
        )
        .order_by(
            "date",
        )
    ):
        rows.extend(
            affected_occurrences_for_time_off_date(
                date_record
            )
        )

    return rows


def time_off_has_complete_coverage(
    time_off_request,
):
    for row in approved_occurrences_needing_coverage(
        time_off_request
    ):
        if not row[
            "existing_override"
        ]:
            return False

    return True


def complete_time_off_admin_task(
    time_off_request,
    *,
    admin_user,
):
    if time_off_request.dates.filter(
        status__in=[
            TeacherTimeOffDate.Status.PENDING,
            TeacherTimeOffDate.Status.COVERAGE_REQUIRED,
        ],
    ).exists():
        return

    task = time_off_request.admin_task

    if not task:
        return

    now = timezone.now()

    task.assignments.filter(
        completed_at__isnull=True,
    ).update(
        completed_at=now,
        completed_by=admin_user,
    )


def notify_teacher_time_off_decision(
    time_off_request,
):
    teacher_user = (
        time_off_request.instructor.user
    )

    if not teacher_user:
        return

    if (
        time_off_request.status
        == TeacherTimeOffRequest.Status.APPROVED
    ):
        kind = (
            TaskNotification.Kind.APPROVED
        )
        title = "Time Off Approved"

    elif (
        time_off_request.status
        == TeacherTimeOffRequest.Status.DENIED
    ):
        kind = (
            TaskNotification.Kind.DENIED
        )
        title = "Time Off Request Denied"

    else:
        kind = (
            TaskNotification.Kind.APPROVED
        )
        title = "Time Off Request Updated"

    approved_count = (
        time_off_request.dates
        .filter(
            status=TeacherTimeOffDate.Status.APPROVED,
        )
        .count()
    )

    denied_count = (
        time_off_request.dates
        .filter(
            status=TeacherTimeOffDate.Status.DENIED,
        )
        .count()
    )

    TaskNotification.objects.create(
        studio=time_off_request.studio,
        user=teacher_user,
        task=time_off_request.admin_task,
        kind=kind,
        title=title,
        message=(
            f"Approved: {approved_count} · "
            f"Denied: {denied_count}"
        ),
    )


def time_off_calendar_items(
    user,
    studio,
    role,
    start_date,
    end_date,
):
    if role not in {
        "administrator",
        "teacher",
    }:
        return []

    rows = (
        TeacherTimeOffDate.objects
        .filter(
            request__studio=studio,
            date__gte=start_date,
            date__lte=end_date,
            status__in=[
                TeacherTimeOffDate.Status.PENDING,
                TeacherTimeOffDate.Status.COVERAGE_REQUIRED,
                TeacherTimeOffDate.Status.APPROVED,
            ],
        )
        .select_related(
            "request",
            "request__instructor",
            "request__instructor__user",
        )
        .order_by(
            "date",
        )
    )

    if role == "teacher":
        rows = rows.filter(
            request__instructor__user=user,
        )

    events = []

    for row in rows:
        pending = (
            row.status
            in {
                TeacherTimeOffDate.Status.PENDING,
                TeacherTimeOffDate.Status.COVERAGE_REQUIRED,
            }
        )

        coverage_required = (
            row.status
            == TeacherTimeOffDate.Status.COVERAGE_REQUIRED
        )

        color = (
            "#C48620"
            if pending
            else "#169C90"
        )

        title = (
            "Coverage Required"
            if coverage_required
            and role == "administrator"
            else "Time Off Requested"
            if pending
            else "Approved Time Off"
        )

        if role == "administrator":
            title = (
                f"{title} · "
                f"{row.request.instructor.full_name}"
            )

        events.append(
            {
                "id": (
                    f"time-off-{row.pk}"
                ),
                "title": title,
                "start": row.date.isoformat(),
                "allDay": True,
                "backgroundColor": color,
                "borderColor": color,
                "extendedProps": {
                    "sourceType": "time_off",
                    "sourceGroup": (
                        "time_off_requested"
                        if pending
                        else "time_off_approved"
                    ),
                    "eventType": (
                        "Requested Time Off"
                        if pending
                        else "Approved Time Off"
                    ),
                    "timeOffRequestId": (
                        row.request_id
                    ),
                    "timeOffDateId": row.pk,
                    "description": (
                        row.request.reason
                    ),
                    "notes": (
                        row.request.notes
                    ),
                    "teacher": (
                        row.request.instructor.full_name
                    ),
                    "editable": False,
                    "deletable": False,
                    "detailUrl": (
                        reverse(
                            "scheduling:time_off_admin_review",
                            kwargs={
                                "studio_slug": studio.slug,
                                "request_id": row.request_id,
                            },
                        )
                        if role == "administrator"
                        else ""
                    ),
                },
            }
        )

    return events


def notify_substitute_assignment(
    override,
):
    user = (
        override.substitute_instructor.user
    )

    if not user:
        return

    TaskNotification.objects.create(
        studio=override.studio,
        user=user,
        task=None,
        kind=TaskNotification.Kind.ASSIGNED,
        title="Substitute Class Assigned",
        message=(
            f"{override.class_instance.name} · "
            f"{override.occurrence_date.strftime('%b %d, %Y')} · "
            f"{override.meeting.start_time.strftime('%-I:%M %p')}"
        ),
    )


def substitute_calendar_items(
    user,
    studio,
    role,
    start_date,
    end_date,
):
    if role not in {
        "administrator",
        "teacher",
    }:
        return []

    overrides = (
        ClassOccurrenceOverride.objects
        .filter(
            studio=studio,
            occurrence_date__gte=start_date,
            occurrence_date__lte=end_date,
            status=ClassOccurrenceOverride.Status.ACTIVE,
            time_off_date__status=TeacherTimeOffDate.Status.APPROVED,
        )
        .select_related(
            "class_instance",
            "meeting",
            "meeting__room",
            "meeting__location",
            "absent_instructor",
            "substitute_instructor",
            "substitute_instructor__user",
        )
        .order_by(
            "occurrence_date",
            "meeting__start_time",
        )
    )

    if role == "teacher":
        overrides = overrides.filter(
            substitute_instructor__user=user,
        )

    events = []

    for override in overrides:
        start_at = timezone.make_aware(
            datetime.combine(
                override.occurrence_date,
                override.meeting.start_time,
            ),
            timezone.get_current_timezone(),
        )

        end_at = (
            start_at
            + timedelta(
                minutes=override.meeting.duration_minutes,
            )
        )

        location_name = ""

        if override.meeting.room_id:
            location_name = (
                override.meeting.room.name
            )

            if (
                override.meeting.room.location_id
            ):
                location_name = (
                    f"{override.meeting.room.name} · "
                    f"{override.meeting.room.location.name}"
                )

        elif override.meeting.location_id:
            location_name = (
                override.meeting.location.name
            )

        title = (
            f"Sub: "
            f"{override.class_instance.name}"
        )

        if role == "administrator":
            title = (
                f"{override.class_instance.name} · "
                f"Sub: "
                f"{override.substitute_instructor.full_name}"
            )

        events.append(
            {
                "id": (
                    f"substitute-"
                    f"{override.pk}"
                ),
                "title": title,
                "start": start_at.isoformat(),
                "end": end_at.isoformat(),
                "allDay": False,
                "backgroundColor": "#7A5AF8",
                "borderColor": "#7A5AF8",
                "extendedProps": {
                    "sourceType": "substitute",
                    "sourceGroup": "substitutes",
                    "eventType": "Substitute Class",
                    "classId": (
                        override.class_instance_id
                    ),
                    "teacher": (
                        override.substitute_instructor.full_name
                    ),
                    "absentTeacher": (
                        override.absent_instructor.full_name
                    ),
                    "location": location_name,
                    "editable": False,
                    "deletable": False,
                    "detailUrl": reverse(
                        "classes:class_detail",
                        kwargs={
                            "studio_slug": studio.slug,
                            "class_id": (
                                override.class_instance_id
                            ),
                        },
                    ),
                },
            }
        )

    return events


def teacher_is_off_for_occurrence(
    user,
    class_instance,
    occurrence_date,
):
    return (
        ClassOccurrenceOverride.objects
        .filter(
            studio=class_instance.studio,
            class_instance=class_instance,
            occurrence_date=occurrence_date,
            absent_instructor__user=user,
            status=ClassOccurrenceOverride.Status.ACTIVE,
            time_off_date__status=TeacherTimeOffDate.Status.APPROVED,
        )
        .exists()
    )



def _minutes_since_midnight(value):
    return (
        value.hour * 60
        + value.minute
    )


def _meeting_window(meeting):
    start = _minutes_since_midnight(
        meeting.start_time
    )

    end = (
        start
        + meeting.duration_minutes
    )

    return start, end


def _windows_overlap(
    start_a,
    end_a,
    start_b,
    end_b,
):
    return (
        start_a < end_b
        and start_b < end_a
    )


def substitute_conflicts_for_occurrence(
    *,
    instructor,
    studio,
    occurrence_date,
    meeting,
    ignore_override_id=None,
):
    """
    Return human-readable reasons this instructor should not
    be selectable as a substitute for one occurrence.
    """
    reasons = []

    if not instructor.is_active:
        reasons.append(
            "Instructor is inactive."
        )

        return reasons

    target_start, target_end = (
        _meeting_window(
            meeting
        )
    )

    # Approved time off, or already admin-approved and waiting
    # for substitute coverage on the instructor's own request.
    has_time_off = (
        TeacherTimeOffDate.objects
        .filter(
            request__studio=studio,
            request__instructor=instructor,
            date=occurrence_date,
            status__in=[
                TeacherTimeOffDate.Status.APPROVED,
                TeacherTimeOffDate.Status.COVERAGE_REQUIRED,
            ],
        )
        .exists()
    )

    if has_time_off:
        reasons.append(
            "Has approved time off that day."
        )

    # Normal class schedule conflicts.
    scheduled_meetings = (
        Class.objects
        .filter(
            studio=studio,
            is_active=True,
            season__start_date__lte=occurrence_date,
            season__end_date__gte=occurrence_date,
        )
        .filter(
            Q(instructor=instructor)
            | Q(
                assistant_instructor=instructor
            )
        )
        .values_list(
            "meeting_times__id",
            flat=True,
        )
    )

    from classes.models import ClassMeeting

    conflicting_meetings = (
        ClassMeeting.objects
        .filter(
            pk__in=scheduled_meetings,
            is_active=True,
            day_of_week=occurrence_date.weekday(),
        )
        .select_related(
            "class_instance",
        )
    )

    for scheduled in conflicting_meetings:
        scheduled_start, scheduled_end = (
            _meeting_window(
                scheduled
            )
        )

        if _windows_overlap(
            target_start,
            target_end,
            scheduled_start,
            scheduled_end,
        ):
            reasons.append(
                (
                    "Already teaching "
                    f"{scheduled.class_instance.name} "
                    f"at "
                    f"{scheduled.start_time.strftime('%-I:%M %p')}."
                )
            )

    # Existing substitute assignment conflicts.
    substitute_overrides = (
        ClassOccurrenceOverride.objects
        .filter(
            studio=studio,
            occurrence_date=occurrence_date,
            substitute_instructor=instructor,
            status=ClassOccurrenceOverride.Status.ACTIVE,
            time_off_date__status=TeacherTimeOffDate.Status.APPROVED,
        )
        .select_related(
            "class_instance",
            "meeting",
        )
    )

    if ignore_override_id:
        substitute_overrides = (
            substitute_overrides.exclude(
                pk=ignore_override_id,
            )
        )

    for override in substitute_overrides:
        override_start, override_end = (
            _meeting_window(
                override.meeting
            )
        )

        if _windows_overlap(
            target_start,
            target_end,
            override_start,
            override_end,
        ):
            reasons.append(
                (
                    "Already substituting for "
                    f"{override.class_instance.name} "
                    f"at "
                    f"{override.meeting.start_time.strftime('%-I:%M %p')}."
                )
            )

    return reasons


def substitute_availability_for_occurrence(
    *,
    studio,
    absent_instructor,
    occurrence_date,
    meeting,
    existing_override=None,
):
    instructors = (
        Instructor.objects
        .filter(
            studio=studio,
            is_active=True,
        )
        .exclude(
            pk=absent_instructor.pk,
        )
        .order_by(
            "last_name",
            "first_name",
        )
    )

    available_ids = []
    unavailable = []

    for instructor in instructors:
        conflicts = (
            substitute_conflicts_for_occurrence(
                instructor=instructor,
                studio=studio,
                occurrence_date=occurrence_date,
                meeting=meeting,
                ignore_override_id=(
                    existing_override.pk
                    if existing_override
                    else None
                ),
            )
        )

        if conflicts:
            unavailable.append(
                {
                    "instructor": instructor,
                    "reasons": conflicts,
                }
            )

            continue

        available_ids.append(
            instructor.pk
        )

    # Preserve an already-selected substitute in the dropdown
    # so an existing record remains visible while editing,
    # even if a later schedule change introduced a conflict.
    if (
        existing_override
        and existing_override.substitute_instructor_id
        not in available_ids
    ):
        available_ids.append(
            existing_override.substitute_instructor_id
        )

    return {
        "available_ids": available_ids,
        "unavailable": unavailable,
    }
