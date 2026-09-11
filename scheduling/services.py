from dataclasses import dataclass
from datetime import date, datetime, timedelta

from django.db.models import Q
from django.utils import timezone

from classes.models import Class
from enrollments.models import Enrollment
from families.models import Guardian
from instructors.models import Instructor
from students.models import Student

from .models import CalendarEvent


@dataclass(frozen=True)
class ClassOccurrence:
    class_id: int
    class_code: str
    class_name: str
    date: date
    start_at: datetime
    end_at: datetime
    instructor_name: str
    location_name: str


def generate_class_occurrences(class_instance, start_date, end_date):
    """
    Generate recurring class occurrences from Season + ClassMeeting records.

    No database row is stored for each weekly occurrence.
    """
    if start_date > end_date:
        return []

    season_start = class_instance.season.start_date
    season_end = class_instance.season.end_date

    effective_start = max(start_date, season_start)
    effective_end = min(end_date, season_end)

    if effective_start > effective_end:
        return []

    current_timezone = timezone.get_current_timezone()
    occurrences = []

    for meeting in class_instance.meeting_times.filter(is_active=True):
        days_until_meeting = (
            meeting.day_of_week - effective_start.weekday()
        ) % 7

        current_date = effective_start + timedelta(days=days_until_meeting)

        while current_date <= effective_end:
            naive_start = datetime.combine(current_date, meeting.start_time)
            start_at = timezone.make_aware(
                naive_start,
                current_timezone,
            )

            end_at = start_at + timedelta(
                minutes=meeting.duration_minutes,
            )

            location = meeting.location or class_instance.default_location

            occurrences.append(
                ClassOccurrence(
                    class_id=class_instance.pk,
                    class_code=class_instance.class_id,
                    class_name=class_instance.name,
                    date=current_date,
                    start_at=start_at,
                    end_at=end_at,
                    instructor_name=class_instance.instructor.full_name,
                    location_name=location.name if location else "",
                )
            )

            current_date += timedelta(days=7)

    return sorted(
        occurrences,
        key=lambda occurrence: occurrence.start_at,
    )


def get_user_role_for_studio(user, studio):
    if user.is_superuser:
        return "administrator"

    membership = (
        user.studio_memberships
        .filter(
            studio=studio,
            is_active=True,
        )
        .first()
    )

    return membership.role if membership else None


def get_visible_classes_for_user(user, studio):
    """
    Determine which classes belong on a user's personal calendar.
    """
    role = get_user_role_for_studio(user, studio)

    base_qs = (
        Class.objects
        .filter(
            studio=studio,
            is_active=True,
        )
        .select_related(
            "season",
            "class_type",
            "instructor",
            "assistant_instructor",
            "default_location",
        )
        .prefetch_related(
            "meeting_times",
        )
    )

    if role == "administrator":
        return base_qs

    if role == "teacher":
        instructor = (
            Instructor.objects
            .filter(
                studio=studio,
                user=user,
                is_active=True,
            )
            .first()
        )

        if not instructor:
            return base_qs.none()

        return base_qs.filter(
            Q(instructor=instructor)
            | Q(assistant_instructor=instructor)
        ).distinct()

    if role == "student":
        student = (
            Student.objects
            .filter(
                studio=studio,
                user=user,
                is_active=True,
            )
            .first()
        )

        if not student:
            return base_qs.none()

        class_ids = (
            Enrollment.objects
            .filter(
                student=student,
                status=Enrollment.Status.ACTIVE,
            )
            .values_list(
                "class_instance_id",
                flat=True,
            )
        )

        return base_qs.filter(pk__in=class_ids)

    if role == "family":
        guardian = (
            Guardian.objects
            .filter(
                family__studio=studio,
                user=user,
                is_active=True,
            )
            .select_related("family")
            .first()
        )

        if not guardian:
            return base_qs.none()

        student_ids = (
            guardian.family.students
            .filter(is_active=True)
            .values_list("pk", flat=True)
        )

        class_ids = (
            Enrollment.objects
            .filter(
                student_id__in=student_ids,
                status=Enrollment.Status.ACTIVE,
            )
            .values_list(
                "class_instance_id",
                flat=True,
            )
        )

        return base_qs.filter(pk__in=class_ids).distinct()

    return base_qs.none()


def get_visible_calendar_events_for_user(user, studio):
    """
    Return operational calendar events a user may see.
    """
    role = get_user_role_for_studio(user, studio)

    base_qs = (
        CalendarEvent.objects
        .filter(
            studio=studio,
            is_active=True,
        )
        .select_related(
            "class_instance",
            "instructor",
        )
    )

    if role == "administrator":
        return base_qs

    if role == "teacher":
        instructor = (
            Instructor.objects
            .filter(
                studio=studio,
                user=user,
                is_active=True,
            )
            .first()
        )

        visible_class_ids = get_visible_classes_for_user(
            user,
            studio,
        ).values_list("pk", flat=True)

        return base_qs.filter(
            Q(audience=CalendarEvent.Audience.STUDIO)
            | Q(audience=CalendarEvent.Audience.TEACHERS)
            | Q(
                audience=CalendarEvent.Audience.CLASS_MEMBERS,
                class_instance_id__in=visible_class_ids,
            )
            | Q(instructor=instructor)
        ).distinct()

    if role in {"student", "family"}:
        visible_class_ids = get_visible_classes_for_user(
            user,
            studio,
        ).values_list("pk", flat=True)

        return base_qs.filter(
            Q(audience=CalendarEvent.Audience.STUDIO)
            | Q(
                audience=CalendarEvent.Audience.CLASS_MEMBERS,
                class_instance_id__in=visible_class_ids,
            )
        ).distinct()

    return base_qs.none()
