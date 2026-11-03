from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from communications.models import (
    NotificationPreference,
    WorkspaceNotification,
)
from communications.notification_services import create_workspace_notification
from families.models import Guardian
from tasks.models import Task, TaskAssignment


def _assignment_users(assignment):
    if (
        assignment.recipient_type == TaskAssignment.RecipientType.USER
        and assignment.user_id
    ):
        return [assignment.user]

    student = assignment.student
    if student is None:
        return []

    recipients = []
    if student.user_id:
        recipients.append(student.user)

    if student.family_id:
        recipients.extend(
            guardian.user
            for guardian in Guardian.objects.filter(
                family_id=student.family_id,
                is_active=True,
                user__isnull=False,
            ).select_related("user")
        )

    seen = set()
    result = []
    for user in recipients:
        if user.pk in seen:
            continue
        seen.add(user.pk)
        result.append(user)
    return result


class Command(BaseCommand):
    help = "Create due-soon and overdue task notifications from user preferences."

    def handle(self, *args, **options):
        today = timezone.localdate()
        created_count = 0

        tasks = (
            Task.objects
            .filter(
                is_active=True,
                due_date__isnull=False,
            )
            .exclude(approval_status=Task.ApprovalStatus.DENIED)
            .prefetch_related(
                "assignments__user",
                "assignments__student__user",
                "assignments__student__family__guardians__user",
            )
        )

        for task in tasks:
            for assignment in task.assignments.all():
                if assignment.completed_at:
                    continue

                for user in _assignment_users(assignment):
                    preference = NotificationPreference.objects.filter(
                        studio=task.studio,
                        user=user,
                    ).first()

                    reminder_enabled = (
                        preference.task_due_reminder
                        if preference
                        else True
                    )
                    reminder_days = (
                        preference.task_due_reminder_days
                        if preference
                        else 2
                    )
                    overdue_enabled = (
                        preference.task_overdue
                        if preference
                        else True
                    )

                    if (
                        reminder_enabled
                        and task.due_date == today + timedelta(days=reminder_days)
                    ):
                        item = create_workspace_notification(
                            studio=task.studio,
                            user=user,
                            category=WorkspaceNotification.Category.TASK,
                            kind="task_due_soon",
                            title="Task Due Soon",
                            message=(
                                f"{task.title} is due in "
                                f"{reminder_days} day"
                                f"{'s' if reminder_days != 1 else ''}."
                            ),
                            action_url=f"/tasks/{task.studio.slug}/{task.pk}/",
                            dedupe_key=(
                                f"task-due-{task.pk}-{assignment.pk}-"
                                f"{task.due_date.isoformat()}-{reminder_days}"
                            ),
                            preference_field="task_due_reminder",
                        )
                        created_count += int(item is not None)

                    if overdue_enabled and task.due_date < today:
                        item = create_workspace_notification(
                            studio=task.studio,
                            user=user,
                            category=WorkspaceNotification.Category.TASK,
                            kind="task_overdue",
                            title="Task Overdue",
                            message=f"{task.title} was due {task.due_date:%b %d}.",
                            action_url=f"/tasks/{task.studio.slug}/{task.pk}/",
                            dedupe_key=(
                                f"task-overdue-{task.pk}-{assignment.pk}-"
                                f"{task.due_date.isoformat()}"
                            ),
                            preference_field="task_overdue",
                        )
                        created_count += int(item is not None)

        self.stdout.write(
            self.style.SUCCESS(
                f"Created {created_count} task notification(s)."
            )
        )
