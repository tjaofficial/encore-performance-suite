"""Keep student-facing make-up checklist tasks aligned with attendance obligations.

Only finalized attendance requirements are counted here. Future approved absence
requests are handled when their attendance records become finalized (Phase 3).
"""
from django.db import transaction
from django.utils import timezone

from tasks.models import Task, TaskAssignment
from communications.notification_services import notify_student_guardians
from .models import MakeupAssignment, MakeupRequirement


@transaction.atomic
def sync_makeup_tasks(student):
    """Create/update exactly one Schedule and one Attend task for this student.

    Schedule counts outstanding requirements without an active reservation.
    Attend counts all outstanding requirements, regardless of booking.
    """
    requirements = list(
        MakeupRequirement.objects.filter(
            student=student,
            status=MakeupRequirement.Status.OUTSTANDING,
        ).prefetch_related("assignments")
    )
    outstanding = len(requirements)
    unscheduled = sum(
        not any(
            item.status in {MakeupAssignment.Status.SCHEDULED, MakeupAssignment.Status.COMPLETED}
            for item in requirement.assignments.all()
        )
        for requirement in requirements
    )
    for kind, remaining, verb in (
        ("schedule", unscheduled, "Schedule"),
        ("attend", outstanding, "Attend"),
    ):
        marker = f"[Encore make-up tracker:{kind}]"
        task = Task.objects.filter(
            studio=student.studio, student=student,
            description__startswith=marker,
        ).order_by("pk").first()
        if task is None and outstanding == 0:
            continue
        title = f"{verb} {remaining} Make-Up Day{'s' if remaining != 1 else ''}"
        description = (
            f"{marker}\n{student.first_name} has {remaining} make-up "
            f"day{'s' if remaining != 1 else ''} remaining to {kind}. "
            "This task updates automatically when make-ups are booked and attended."
        )
        if task is None:
            task = Task.objects.create(
                studio=student.studio, student=student,
                title=title, description=description,
                priority=Task.Priority.NORMAL,
                context_type=Task.ContextType.STUDENT,
                audience_type=Task.AudienceType.RELATED_STUDENT,
                is_student_facing=True,
                notify_assignees=True,
            )
        elif task.title != title or task.description != description or not task.is_active:
            task.title = title
            task.description = description
            task.is_active = True
            task.save(update_fields=["title", "description", "is_active", "updated_at"])
        assignment, _ = TaskAssignment.objects.get_or_create(
            task=task,
            recipient_type=TaskAssignment.RecipientType.STUDENT,
            student=student,
        )
        if remaining == 0 and assignment.completed_at is None:
            assignment.completed_at = timezone.now()
            assignment.completed_by = None
            assignment.reopened_at = None
            assignment.save(update_fields=["completed_at", "completed_by", "reopened_at"])
        elif remaining > 0 and assignment.completed_at is not None:
            assignment.reopen()

    # One-time notices per outstanding obligation (not each mutable task title).
    from django.urls import reverse
    schedule_url = reverse("attendance:makeup_schedule", kwargs={"studio_slug": student.studio.slug})
    schedule_url += f"?student={student.pk}"
    for requirement in requirements:
        assignments = requirement.assignments.all()
        booked = any(a.status in {MakeupAssignment.Status.SCHEDULED, MakeupAssignment.Status.COMPLETED} for a in assignments)
        if not booked:
            notify_student_guardians(
                student, kind="makeup_task_schedule", title="Make-Up Scheduling Required",
                message=f"{student.first_name} has a make-up class to schedule for {requirement.source_class.name}.",
                action_url=schedule_url, event_key=f"makeup-obligation-schedule:{requirement.pk}",
            )
        notify_student_guardians(
            student, kind="makeup_task_attend", title="Make-Up Attendance Required",
            message=f"{student.first_name} needs to attend a make-up class for {requirement.source_class.name}.",
            action_url=schedule_url, event_key=f"makeup-obligation-attend:{requirement.pk}",
        )
