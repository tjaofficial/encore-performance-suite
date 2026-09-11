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
    stale_after_days=180,
):
    draft = current_draft_measurement(
        student
    )

    if draft and draft.has_measurements:
        return "in_progress"

    completed = current_completed_measurement(
        student
    )

    if completed is None:
        return "not_started"

    if (
        completed.measured_at
        and (
            timezone.now()
            - completed.measured_at
        ).days
        >= stale_after_days
    ):
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
        studio=studio,
        student=student,
        is_complete=False,
    ).delete()

    return StudentMeasurementSet.objects.create(
        studio=studio,
        student=student,
        measured_by=user,
    )


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

    active_student_ids = list(
        Enrollment.objects
        .filter(
            class_instance=class_instance,
            status=Enrollment.Status.ACTIVE,
        )
        .values_list(
            "student_id",
            flat=True,
        )
    )

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
