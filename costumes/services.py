from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from communications.models import Announcement
from enrollments.models import Enrollment
from families.models import Guardian
from studios.models import StudioMembership
from tasks.models import Task
from tasks.services import synchronize_task_assignments

from .models import (
    Costume,
    StudentCostumeAssignment,
    StudentMeasurementSet,
    VendorSizeChart,
)

User = get_user_model()


def workspace_role(
    request,
    studio,
):
    role = request.session.get(
        "encore_workspace_role"
    )

    selected_studio = request.session.get(
        "encore_workspace_studio_slug"
    )

    if selected_studio != studio.slug:
        return None

    if (
        request.user.is_superuser
        and role
        == StudioMembership.Role.ADMINISTRATOR
    ):
        return role

    if role not in {
        StudioMembership.Role.ADMINISTRATOR,
        StudioMembership.Role.TEACHER,
        StudioMembership.Role.FAMILY,
        StudioMembership.Role.STUDENT,
    }:
        return None

    if request.user.studio_memberships.filter(
        studio=studio,
        role=role,
        is_active=True,
    ).exists():
        return role

    return None


def teacher_can_manage_class(
    user,
    class_instance,
):
    return (
        (
            class_instance.instructor_id
            and class_instance.instructor.user_id
            == user.id
        )
        or (
            class_instance.assistant_instructor_id
            and class_instance.assistant_instructor.user_id
            == user.id
        )
    )


def can_manage_class(
    request,
    studio,
    class_instance,
):
    role = workspace_role(
        request,
        studio,
    )

    if (
        role
        == StudioMembership.Role.ADMINISTRATOR
    ):
        return True

    if (
        role
        == StudioMembership.Role.TEACHER
        and teacher_can_manage_class(
            request.user,
            class_instance,
        )
    ):
        return True

    return False


def current_completed_measurement(
    student,
):
    return (
        student.measurement_sets
        .filter(
            is_complete=True,
        )
        .order_by(
            "-measured_at",
            "-updated_at",
        )
        .first()
    )


def current_draft_measurement(
    student,
):
    return (
        student.measurement_sets
        .filter(
            is_complete=False,
        )
        .order_by(
            "-updated_at",
        )
        .first()
    )


def measurement_state(
    student,
    *,
    stale_after_days=None,
):
    draft = current_draft_measurement(student)
    if draft and draft.has_measurements:
        return "in_progress"

    completed = current_completed_measurement(student)
    if completed is None:
        return "not_started"

    if stale_after_days is None:
        settings_obj = getattr(student.studio, "settings", None)
        months = getattr(settings_obj, "remeasurement_interval_months", 6)
        stale_after_days = max(int(months or 6), 1) * 30

    if completed.measured_at and (timezone.now() - completed.measured_at).days >= stale_after_days:
        return "needs_remeasurement"
    return "complete"


@transaction.atomic
def get_or_create_measurement_draft(
    student,
    studio,
    user=None,
):
    draft = current_draft_measurement(
        student
    )

    if draft is not None:
        return draft

    return StudentMeasurementSet.objects.create(
        studio=studio,
        student=student,
        measured_by=user,
    )


@transaction.atomic
def start_new_measurement_set(
    student,
    studio,
    user=None,
):
    StudentMeasurementSet.objects.filter(
        studio=studio, student=student, is_complete=False
    ).delete()

    current = current_completed_measurement(student)
    values = {}
    if current is not None:
        for field_name in (
            "bust", "waist", "hips", "girth", "inseam", "outseam",
            "height", "clothing_size", "shoe_size", "other_size_info", "notes",
        ):
            values[field_name] = getattr(current, field_name)

    return StudentMeasurementSet.objects.create(
        studio=studio, student=student, measured_by=user, **values
    )


@transaction.atomic
def cancel_measurement_draft(student, studio):
    StudentMeasurementSet.objects.filter(
        studio=studio, student=student, is_complete=False
    ).delete()
    return current_completed_measurement(student)


def measurement_to_display(value, unit):
    if value is None:
        return None
    if unit == "cm":
        return round(float(value) * 2.54, 2)
    return float(value)


def measurement_from_display(value, unit):
    if value is None:
        return None
    if unit == "cm":
        return value / 2.54
    return value


MEASUREMENT_RANGE_FIELDS = (
    "bust", "waist", "hips", "girth", "height"
)

MEASUREMENT_SINGLE_FIELDS = (
    "inseam", "outseam"
)

MEASUREMENT_CONVERSION_FIELDS = (
    *MEASUREMENT_RANGE_FIELDS,
    *MEASUREMENT_SINGLE_FIELDS,
)


def _chart_matches_student(chart, student):
    if student is None:
        return True

    if chart.gender == chart.Gender.ALL:
        return True

    return bool(
        student.gender
        and chart.gender == student.gender
    )


def _entry_matches_age(entry, student_age):
    if student_age is None:
        return True

    if entry.age_min is not None and student_age < entry.age_min:
        return False

    if entry.age_max is not None and student_age > entry.age_max:
        return False

    return True


def chart_size_for_field(
    chart,
    field_name,
    value,
    *,
    student=None,
):
    if value is None or field_name not in MEASUREMENT_CONVERSION_FIELDS:
        return None

    if not _chart_matches_student(chart, student):
        return None

    student_age = getattr(student, "age", None) if student is not None else None

    for entry in chart.entries.all():
        if not _entry_matches_age(entry, student_age):
            continue

        if field_name in MEASUREMENT_SINGLE_FIELDS:
            target = getattr(entry, f"{field_name}_min")
            if target is None:
                continue
            if value == target:
                return entry.size_label
            continue

        minimum = getattr(entry, f"{field_name}_min")
        maximum = getattr(entry, f"{field_name}_max")

        if minimum is None and maximum is None:
            continue
        if minimum is not None and value < minimum:
            continue
        if maximum is not None and value > maximum:
            continue

        return entry.size_label

    return None


def vendor_measurement_conversions(vendor, measurement_set):
    if not vendor or not measurement_set:
        return []

    student = getattr(measurement_set, "student", None)
    charts = list(
        vendor.size_charts
        .filter(is_active=True)
        .prefetch_related("entries")
    )

    charts = [
        chart
        for chart in charts
        if _chart_matches_student(chart, student)
    ]

    results = []

    for field_name in MEASUREMENT_CONVERSION_FIELDS:
        value = getattr(measurement_set, field_name, None)
        if value is None:
            continue

        chart_results = []
        for chart in charts:
            size = chart_size_for_field(
                chart,
                field_name,
                value,
                student=student,
            )
            if size:
                chart_results.append(
                    {
                        "chart": chart.name,
                        "size": size,
                    }
                )

        results.append(
            {
                "field": field_name,
                "value": value,
                "charts": chart_results,
            }
        )

    return results


def recommend_size_for_chart(chart, measurement_set):
    if not chart or not measurement_set:
        return None

    student = getattr(measurement_set, "student", None)
    if not _chart_matches_student(chart, student):
        return None

    student_age = getattr(student, "age", None) if student is not None else None
    best = []

    for entry in chart.entries.all():
        if not _entry_matches_age(entry, student_age):
            continue

        comparable = 0
        matches = 0

        for field_name in MEASUREMENT_RANGE_FIELDS:
            value = getattr(measurement_set, field_name, None)
            minimum = getattr(entry, f"{field_name}_min")
            maximum = getattr(entry, f"{field_name}_max")

            if value is None or (minimum is None and maximum is None):
                continue

            comparable += 1
            if (
                (minimum is None or value >= minimum)
                and (maximum is None or value <= maximum)
            ):
                matches += 1

        for field_name in MEASUREMENT_SINGLE_FIELDS:
            value = getattr(measurement_set, field_name, None)
            target = getattr(entry, f"{field_name}_min")

            if value is None or target is None:
                continue

            comparable += 1
            if value == target:
                matches += 1

        if comparable:
            best.append(
                (matches, comparable, entry.sort_order, entry.size_label)
            )

    if not best:
        return None

    full = [row for row in best if row[0] == row[1]]
    if len(full) == 1:
        return full[0][3]

    if len(full) > 1:
        full.sort(key=lambda x: (-x[1], x[2]))
        if len(full) == 1 or full[0][1] > full[1][1]:
            return full[0][3]
        return "Review Size"

    best.sort(key=lambda x: (-x[0], -x[1], x[2]))
    return "Review Size" if best[0][0] else None


def latest_measurement_for_assignment(
    student,
):
    return current_completed_measurement(
        student
    )


@transaction.atomic
def sync_costume_assignments(
    costume,
):
    class_instance = (
        costume.dance.class_instance
    )

    enrollment_qs = Enrollment.objects.filter(
        class_instance=class_instance,
        status=Enrollment.Status.ACTIVE,
    )
    if costume.gender_scope != Costume.GenderScope.ALL:
        enrollment_qs = enrollment_qs.filter(
            student__gender=costume.gender_scope
        )
    active_student_ids = list(enrollment_qs.values_list("student_id", flat=True))

    existing = {
        assignment.student_id: assignment
        for assignment
        in costume.student_assignments.all()
    }

    for student_id in active_student_ids:
        if student_id in existing:
            assignment = existing[
                student_id
            ]

            if not assignment.is_active:
                assignment.is_active = True
                assignment.save(
                    update_fields=[
                        "is_active",
                        "updated_at",
                    ]
                )

            continue

        from students.models import Student

        student = Student.objects.get(
            pk=student_id
        )

        measurement_set = (
            latest_measurement_for_assignment(
                student
            )
        )

        status = (
            StudentCostumeAssignment.Status.MEASUREMENTS_READY
            if measurement_set
            else StudentCostumeAssignment.Status.NOT_STARTED
        )

        StudentCostumeAssignment.objects.create(
            costume=costume,
            student=student,
            measurement_set_used=measurement_set,
            shoe_size=(
                measurement_set.shoe_size
                if measurement_set
                else ""
            ),
            status=status,
        )

    costume.student_assignments.exclude(
        student_id__in=active_student_ids,
    ).update(
        is_active=False,
    )


def create_costume_student_task(
    costume,
    *,
    creator,
    role,
    due_date=None,
):
    class_instance = (
        costume.dance.class_instance
    )

    task = Task.objects.create(
        studio=costume.studio,
        title=(
            "Review costume information: "
            f"{costume.dance.title or costume.name}"
        ),
        description=(
            costume.student_notes
            or (
                "Review the costume information, "
                "photos, links, and instructions."
            )
        ),
        priority=Task.Priority.NORMAL,
        due_date=due_date,
        created_by=creator,
        context_type=Task.ContextType.CLASS,
        audience_type=(
            Task.AudienceType.ALL_STUDENTS_IN_CLASS
        ),
        class_instance=class_instance,
        is_student_facing=True,
        notify_assignees=True,
    )

    synchronize_task_assignments(
        task,
        creator=creator,
        role=role,
    )

    return task


def create_costume_announcement(
    costume,
    *,
    creator,
):
    class_instance = (
        costume.dance.class_instance
    )

    announcement = Announcement.objects.create(
        studio=costume.studio,
        title="New Costume Information Available",
        message=(
            f"{costume.dance.title or costume.name}: "
            "costume photos, purchase links, "
            "and instructions are now available."
        ),
        audience=Announcement.Audience.CLASS,
        priority=Announcement.Priority.NORMAL,
        is_published=True,
        created_by=creator,
    )

    announcement.classes.add(
        class_instance
    )

    return announcement


def family_student_ids(
    user,
    studio,
):
    return list(
        Guardian.objects
        .filter(
            user=user,
            is_active=True,
            family__studio=studio,
        )
        .values_list(
            "family__students__id",
            flat=True,
        )
        .distinct()
    )
