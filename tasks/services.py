from datetime import timedelta
import hashlib

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import (
    Case,
    IntegerField,
    Q,
    Value,
    When,
)
from django.utils import timezone

from enrollments.models import Enrollment
from families.models import Guardian
from instructors.models import Instructor
from studios.models import StudioMembership

from communications.models import WorkspaceNotification
from communications.notification_services import (
    create_workspace_notification,
    notification_enabled,
)

from .models import (
    Task,
    TaskAssignment,
    TaskCompletion,
    TaskNotification,
    TaskTemplate,
    TaskTemplateItem,
    TaskTemplateRun,
    TaskTemplateTrigger,
)

User = get_user_model()


def selected_workspace_role(request, studio):
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
        and role == StudioMembership.Role.ADMINISTRATOR
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


def teacher_class_ids(user, studio):
    instructor = Instructor.objects.filter(
        studio=studio,
        user=user,
        is_active=True,
    ).first()

    if instructor is None:
        return []

    ids = set(
        instructor.primary_classes.filter(
            is_active=True,
        ).values_list(
            "id",
            flat=True,
        )
    )

    ids.update(
        instructor.assistant_classes.filter(
            is_active=True,
        ).values_list(
            "id",
            flat=True,
        )
    )

    return list(ids)


def task_assignment_for_user(
    task,
    user,
    role,
):
    direct = task.assignments.filter(
        recipient_type=TaskAssignment.RecipientType.USER,
        user=user,
    ).first()

    if direct:
        return direct

    if role == StudioMembership.Role.STUDENT:
        student = getattr(
            user,
            "student_profile",
            None,
        )

        if student:
            return task.assignments.filter(
                recipient_type=TaskAssignment.RecipientType.STUDENT,
                student=student,
            ).first()

    if role == StudioMembership.Role.FAMILY:
        student_ids = Guardian.objects.filter(
            user=user,
            is_active=True,
            family__studio=task.studio,
        ).values_list(
            "family__students__id",
            flat=True,
        )

        return task.assignments.filter(
            recipient_type=TaskAssignment.RecipientType.STUDENT,
            student_id__in=student_ids,
        ).first()

    return None


def visible_tasks_for_user(
    user,
    studio,
    role,
):
    priority_order = Case(
        When(
            priority=Task.Priority.URGENT,
            then=Value(0),
        ),
        When(
            priority=Task.Priority.HIGH,
            then=Value(1),
        ),
        When(
            priority=Task.Priority.NORMAL,
            then=Value(2),
        ),
        When(
            priority=Task.Priority.LOW,
            then=Value(3),
        ),
        default=Value(4),
        output_field=IntegerField(),
    )

    query = Q(
        assignments__recipient_type=TaskAssignment.RecipientType.USER,
        assignments__user=user,
    )

    if role == StudioMembership.Role.TEACHER:
        query |= Q(
            created_by=user,
        )

        query |= Q(
            context_type=Task.ContextType.CLASS,
            class_instance_id__in=teacher_class_ids(
                user,
                studio,
            ),
        )

    elif role == StudioMembership.Role.ADMINISTRATOR:
        query |= Q(
            created_by=user,
        )

        query |= Q(
            context_type=Task.ContextType.ADMIN,
            approval_status=Task.ApprovalStatus.APPROVED,
        )

    elif role == StudioMembership.Role.STUDENT:
        student = getattr(
            user,
            "student_profile",
            None,
        )

        if student:
            query |= Q(
                assignments__recipient_type=TaskAssignment.RecipientType.STUDENT,
                assignments__student=student,
                is_student_facing=True,
            )

    elif role == StudioMembership.Role.FAMILY:
        family_ids = Guardian.objects.filter(
            user=user,
            is_active=True,
            family__studio=studio,
        ).values_list(
            "family_id",
            flat=True,
        )

        query |= Q(
            assignments__recipient_type=TaskAssignment.RecipientType.STUDENT,
            assignments__student__family_id__in=family_ids,
            is_student_facing=True,
        )

    return (
        Task.objects
        .filter(
            studio=studio,
            is_active=True,
        )
        .filter(query)
        .exclude(
            approval_status=Task.ApprovalStatus.DENIED,
        )
        .select_related(
            "created_by",
            "assigned_to",
            "class_instance",
            "student",
        )
        .prefetch_related(
            "assignments",
        )
        .annotate(
            priority_order=priority_order,
        )
        .order_by(
            "priority_order",
            "due_date",
            "-created_at",
        )
        .distinct()
    )


def _admin_users(studio):
    return User.objects.filter(
        studio_memberships__studio=studio,
        studio_memberships__role=StudioMembership.Role.ADMINISTRATOR,
        studio_memberships__is_active=True,
        is_active=True,
    ).distinct()


def _teacher_users(studio):
    return User.objects.filter(
        studio_memberships__studio=studio,
        studio_memberships__role=StudioMembership.Role.TEACHER,
        studio_memberships__is_active=True,
        is_active=True,
    ).distinct()


def _class_staff_users(class_instance):
    users = []

    for instructor in [
        class_instance.instructor,
        class_instance.assistant_instructor,
    ]:
        if (
            instructor
            and instructor.user_id
            and instructor.user not in users
        ):
            users.append(
                instructor.user
            )

    return users


def notify_task_assignment(
    task,
    user,
    *,
    template_batch=False,
):
    if (
        not user
        or not task.notify_assignees
        or not notification_enabled(
            user,
            task.studio,
            "task_assigned",
        )
    ):
        return

    TaskNotification.objects.create(
        studio=task.studio,
        user=user,
        task=task,
        kind=(
            TaskNotification.Kind.TEMPLATE
            if template_batch
            else TaskNotification.Kind.ASSIGNED
        ),
        title=(
            "New Template Tasks Assigned"
            if template_batch
            else "New Task Assigned"
        ),
        message=(
            f"{task.title} · {task.class_instance.name}"
            if task.class_instance_id
            else task.title
        ),
    )


def _create_user_assignment(
    task,
    user,
    *,
    notify=True,
    template_batch=False,
):
    assignment, created = TaskAssignment.objects.get_or_create(
        task=task,
        recipient_type=TaskAssignment.RecipientType.USER,
        user=user,
    )

    if created and notify:
        notify_task_assignment(
            task,
            user,
            template_batch=template_batch,
        )

    return assignment


def _create_student_assignment(
    task,
    student,
    *,
    notify=True,
    template_batch=False,
):
    assignment, created = TaskAssignment.objects.get_or_create(
        task=task,
        recipient_type=TaskAssignment.RecipientType.STUDENT,
        student=student,
    )

    if created and notify:
        recipients = []

        if student.user_id:
            recipients.append(
                student.user
            )

        if student.family_id:
            recipients.extend(
                guardian.user
                for guardian
                in student.family.guardians.filter(
                    is_active=True,
                    user__isnull=False,
                ).select_related(
                    "user",
                )
            )

        seen = set()

        for user in recipients:
            if user.pk in seen:
                continue

            seen.add(user.pk)

            notify_task_assignment(
                task,
                user,
                template_batch=template_batch,
            )

    return assignment


def synchronize_task_assignments(
    task,
    *,
    creator,
    role,
    selected_teachers=None,
    selected_students=None,
    template_batch=False,
    is_update=False,
):
    previous_user_ids = set(
        task.assignments.filter(
            recipient_type=TaskAssignment.RecipientType.USER,
            user__isnull=False,
        ).values_list(
            "user_id",
            flat=True,
        )
    )

    task.assignments.all().delete()

    selected_teachers = list(
        selected_teachers
        or []
    )
    selected_students = list(
        selected_students
        or []
    )

    audience = task.audience_type

    task.is_student_facing = (
        audience
        in {
            Task.AudienceType.SELECTED_STUDENTS,
            Task.AudienceType.ALL_STUDENTS_IN_CLASS,
            Task.AudienceType.RELATED_STUDENT,
        }
    )

    if audience == Task.AudienceType.SELF:
        _create_user_assignment(
            task,
            creator,
            template_batch=template_batch,
            notify=not is_update,
        )

    elif audience == Task.AudienceType.ADMIN:
        task.context_type = (
            Task.ContextType.ADMIN
        )

        if role != StudioMembership.Role.ADMINISTRATOR:
            raise ValueError(
                "Only an administrator can assign a task to administrators."
            )

        task.approval_status = (
            Task.ApprovalStatus.APPROVED
        )

        # Admin-created Admin tasks are intentionally personal by default:
        # "Admin" means the administrator creating the task, not every admin
        # in the studio. This matches the UI rule that an admin selects Myself.
        _create_user_assignment(
            task,
            creator,
            template_batch=template_batch,
            notify=not is_update,
        )

    elif audience == Task.AudienceType.SELECTED_TEACHERS:
        for user in selected_teachers:
            _create_user_assignment(
                task,
                user,
                template_batch=template_batch,
                notify=not is_update,
            )

    elif audience == Task.AudienceType.ALL_TEACHERS:
        for user in _teacher_users(
            task.studio
        ):
            _create_user_assignment(
                task,
                user,
                template_batch=template_batch,
                notify=not is_update,
            )

    elif audience == Task.AudienceType.CLASS_STAFF:
        if task.class_instance_id:
            for user in _class_staff_users(
                task.class_instance
            ):
                _create_user_assignment(
                    task,
                    user,
                    template_batch=template_batch,
                    notify=not is_update,
                )

    elif audience == Task.AudienceType.SELECTED_STUDENTS:
        for student in selected_students:
            _create_student_assignment(
                task,
                student,
                template_batch=template_batch,
                notify=not is_update,
            )

    elif audience == Task.AudienceType.RELATED_STUDENT:
        related_students = selected_students

        if not related_students and task.student_id:
            related_students = [
                task.student,
            ]

        for student in related_students:
            _create_student_assignment(
                task,
                student,
                template_batch=template_batch,
                notify=not is_update,
            )

    elif audience == Task.AudienceType.ALL_STUDENTS_IN_CLASS:
        if task.class_instance_id:
            enrollments = (
                task.class_instance
                .enrollments
                .filter(
                    status=Enrollment.Status.ACTIVE,
                )
                .select_related(
                    "student",
                    "student__family",
                )
            )

            for enrollment in enrollments:
                _create_student_assignment(
                    task,
                    enrollment.student,
                    template_batch=template_batch,
                    notify=not is_update,
                )

    first_user_assignment = (
        task.assignments
        .filter(
            recipient_type=TaskAssignment.RecipientType.USER,
        )
        .select_related("user")
        .first()
    )

    if audience == Task.AudienceType.ALL_TEACHERS:
        task.assignment_type = (
            Task.AssignmentType.ALL_TEACHERS
        )
        task.assigned_to = None

    elif first_user_assignment:
        task.assignment_type = (
            Task.AssignmentType.USER
        )
        task.assigned_to = (
            first_user_assignment.user
        )

    else:
        task.assignment_type = (
            Task.AssignmentType.SELF
        )
        task.assigned_to = creator

    if is_update:
        current_user_ids = set(
            task.assignments.filter(
                recipient_type=TaskAssignment.RecipientType.USER,
                user__isnull=False,
            ).values_list(
                "user_id",
                flat=True,
            )
        )

        newly_assigned_ids = (
            current_user_ids
            - previous_user_ids
        )

        for reassigned_user in User.objects.filter(
            pk__in=newly_assigned_ids,
            is_active=True,
        ):
            create_workspace_notification(
                studio=task.studio,
                user=reassigned_user,
                category=WorkspaceNotification.Category.TASK,
                kind="task_reassigned",
                title="Task Reassigned",
                message=task.title,
                action_url=f"/tasks/{task.studio.slug}/{task.pk}/",
                dedupe_key=(
                    f"task-reassigned-{task.pk}-"
                    f"{reassigned_user.pk}-"
                    f"{task.updated_at.isoformat()}"
                ),
                preference_field="task_reassigned",
            )

    task.save(
        update_fields=[
            "context_type",
            "is_student_facing",
            "approval_status",
            "approval_requested_at",
            "assignment_type",
            "assigned_to",
            "updated_at",
        ]
    )

def complete_or_reopen_for_user(
    task,
    user,
    role,
):
    if (task.description or "").startswith("[Encore make-up tracker:"):
        # Only the attendance reconciliation service may close/reopen these.
        return None
    assignment = task_assignment_for_user(
        task,
        user,
        role,
    )

    if assignment is None:
        return None

    if assignment.completed_at:
        assignment.reopen()

        TaskCompletion.objects.filter(
            task=task,
            user=user,
        ).delete()

        return False

    assignment.complete(
        user
    )

    TaskCompletion.objects.get_or_create(
        task=task,
        user=user,
    )

    if (
        task.created_by_id
        and task.created_by_id != user.pk
    ):
        create_workspace_notification(
            studio=task.studio,
            user=task.created_by,
            category=WorkspaceNotification.Category.TASK,
            kind="task_completed",
            title="Task Completed",
            message=f"{user.get_full_name() or user.email} completed {task.title}.",
            action_url=f"/tasks/{task.studio.slug}/{task.pk}/",
            dedupe_key=(
                f"task-completed-{task.pk}-"
                f"{assignment.pk}-"
                f"{assignment.completed_at.isoformat()}"
            ),
            preference_field="task_creator_completed",
        )

    return True


def approve_task(
    task,
    admin_user,
    note="",
):
    task.approval_status = (
        Task.ApprovalStatus.APPROVED
    )
    task.approved_by = admin_user
    task.approved_at = timezone.now()
    task.denied_at = None
    task.approval_note = note

    task.save(
        update_fields=[
            "approval_status",
            "approved_by",
            "approved_at",
            "denied_at",
            "approval_note",
            "updated_at",
        ]
    )

    for admin in _admin_users(
        task.studio
    ):
        _create_user_assignment(
            task,
            admin,
            notify=False,
        )

    if task.created_by_id:
        TaskNotification.objects.create(
            studio=task.studio,
            user=task.created_by,
            task=task,
            kind=TaskNotification.Kind.APPROVED,
            title="Task Approved",
            message=task.title,
        )


def deny_task(
    task,
    admin_user,
    note="",
):
    task.approval_status = (
        Task.ApprovalStatus.DENIED
    )
    task.approved_by = admin_user
    task.denied_at = timezone.now()
    task.approved_at = None
    task.approval_note = note
    task.assignments.all().delete()

    task.save(
        update_fields=[
            "approval_status",
            "approved_by",
            "approved_at",
            "denied_at",
            "approval_note",
            "updated_at",
        ]
    )

    if task.created_by_id:
        TaskNotification.objects.create(
            studio=task.studio,
            user=task.created_by,
            task=task,
            kind=TaskNotification.Kind.DENIED,
            title="Task Denied",
            message=task.title,
        )


def _due_date_for_item(
    item,
    *,
    triggered_at,
    related_date=None,
):
    base_date = timezone.localtime(
        triggered_at
    ).date()

    if item.due_rule == TaskTemplateItem.DueRule.NONE:
        return None

    if item.due_rule == TaskTemplateItem.DueRule.SAME_DAY:
        return base_date

    if item.due_rule == TaskTemplateItem.DueRule.DAYS_AFTER:
        return (
            base_date
            + timedelta(
                days=item.due_offset_days,
            )
        )

    if (
        item.due_rule == TaskTemplateItem.DueRule.DAYS_BEFORE
        and related_date
    ):
        return (
            related_date
            - timedelta(
                days=abs(
                    item.due_offset_days
                ),
            )
        )

    return None


def _target_class(target):
    if (
        target
        and target.__class__.__name__ == "Class"
    ):
        return target

    if (
        target
        and target.__class__.__name__ == "Enrollment"
    ):
        return target.class_instance

    return None


def _target_student(target):
    if (
        target
        and target.__class__.__name__ == "Student"
    ):
        return target

    if (
        target
        and target.__class__.__name__ == "Enrollment"
    ):
        return target.student

    return None


@transaction.atomic
def run_task_template(
    template,
    *,
    trigger=None,
    target=None,
    started_by=None,
    occurrence_key=None,
    class_instance=None,
    selected_teachers=None,
    selected_students=None,
):
    now = timezone.now()

    target_ct = (
        ContentType.objects.get_for_model(
            target
        )
        if target is not None
        else None
    )

    target_id = (
        target.pk
        if target is not None
        else None
    )

    occurrence_key = (
        occurrence_key
        or now.strftime(
            "%Y%m%d%H%M"
        )
    )

    raw_key = (
        f"{template.pk}:"
        f"{trigger.pk if trigger else 'manual'}:"
        f"{target_ct.pk if target_ct else 'none'}:"
        f"{target_id or 'none'}:"
        f"{occurrence_key}"
    )

    idempotency_key = hashlib.sha256(
        raw_key.encode(
            "utf-8"
        )
    ).hexdigest()

    existing = TaskTemplateRun.objects.filter(
        idempotency_key=idempotency_key,
    ).first()

    if existing:
        return existing

    run = TaskTemplateRun.objects.create(
        template=template,
        trigger=trigger,
        started_by=started_by,
        target_content_type=target_ct,
        target_object_id=target_id,
        target_label=(
            str(target)
            if target is not None
            else ""
        ),
        idempotency_key=idempotency_key,
        occurrence_key=occurrence_key,
    )

    creator = (
        started_by
        or template.created_by
    )

    creator_role = (
        StudioMembership.Role.ADMINISTRATOR
        if creator.studio_memberships.filter(
            studio=template.studio,
            role=StudioMembership.Role.ADMINISTRATOR,
            is_active=True,
        ).exists()
        else StudioMembership.Role.TEACHER
    )

    generated = []

    try:
        for item in template.items.all():
            context_class = (
                class_instance
                or _target_class(
                    target
                )
            )

            context_student = _target_student(
                target
            )

            task = Task.objects.create(
                studio=template.studio,
                title=item.title,
                description=item.description,
                priority=item.priority,
                due_date=_due_date_for_item(
                    item,
                    triggered_at=now,
                ),
                created_by=creator,
                context_type=item.context_type,
                audience_type=item.audience_type,
                class_instance=context_class,
                student=context_student,
                notify_assignees=item.notify_assignees,
                source_template=template,
                source_template_run=run,
            )

            config = (
                item.assignment_config
                or {}
            )

            configured_teacher_ids = config.get(
                "teacher_user_ids",
                [],
            )

            configured_student_ids = config.get(
                "student_ids",
                [],
            )

            item_teachers = (
                list(
                    User.objects.filter(
                        pk__in=configured_teacher_ids,
                    )
                )
                if configured_teacher_ids
                else list(
                    selected_teachers
                    or []
                )
            )

            item_students = (
                list(
                    template.studio.students.filter(
                        pk__in=configured_student_ids,
                    )
                )
                if configured_student_ids
                else list(
                    selected_students
                    or []
                )
            )

            if (
                item.audience_type
                == Task.AudienceType.RELATED_STUDENT
                and context_student
                and not item_students
            ):
                item_students = [
                    context_student,
                ]

            synchronize_task_assignments(
                task,
                creator=creator,
                role=creator_role,
                selected_teachers=item_teachers,
                selected_students=item_students,
                template_batch=True,
            )

            generated.append(task)

        run.status = (
            TaskTemplateRun.Status.COMPLETE
        )
        run.tasks_created_count = len(
            generated
        )
        run.completed_at = timezone.now()
        run.save(
            update_fields=[
                "status",
                "tasks_created_count",
                "completed_at",
            ]
        )

        if trigger:
            trigger.last_run_at = (
                timezone.now()
            )
            trigger.save(
                update_fields=[
                    "last_run_at",
                ]
            )

    except Exception as error:
        run.status = (
            TaskTemplateRun.Status.FAILED
        )
        run.error_message = str(
            error
        )[:4000]
        run.completed_at = timezone.now()
        run.save(
            update_fields=[
                "status",
                "error_message",
                "completed_at",
            ]
        )
        raise

    return run


def run_event_templates(
    studio,
    trigger_type,
    target,
):
    triggers = (
        TaskTemplateTrigger.objects
        .filter(
            template__studio=studio,
            template__status=TaskTemplate.Status.ACTIVE,
            trigger_type=trigger_type,
            is_enabled=True,
        )
        .select_related(
            "template",
        )
    )

    for trigger in triggers:
        run_task_template(
            trigger.template,
            trigger=trigger,
            target=target,
            occurrence_key=(
                f"object-{target.pk}"
            ),
        )


def scheduled_trigger_is_due(
    trigger,
    now=None,
):
    now = now or timezone.now()
    config = trigger.configuration or {}
    local_now = timezone.localtime(now)

    run_time = config.get(
        "run_time"
    )

    if not run_time:
        return False

    try:
        hour, minute = [
            int(part)
            for part
            in run_time.split(
                ":",
                1,
            )
        ]
    except (
        TypeError,
        ValueError,
    ):
        return False

    if (
        local_now.hour,
        local_now.minute,
    ) < (
        hour,
        minute,
    ):
        return False

    if (
        trigger.trigger_type
        == TaskTemplateTrigger.TriggerType.SPECIFIC_DATETIME
    ):
        return (
            config.get("run_date")
            == local_now.date().isoformat()
        )

    if (
        trigger.trigger_type
        == TaskTemplateTrigger.TriggerType.RECURRING
    ):
        return (
            local_now.weekday()
            in config.get(
                "weekdays",
                [],
            )
        )

    return False


def run_due_scheduled_templates(
    now=None,
):
    now = now or timezone.now()

    triggers = (
        TaskTemplateTrigger.objects
        .filter(
            template__status=TaskTemplate.Status.ACTIVE,
            trigger_type__in=[
                TaskTemplateTrigger.TriggerType.SPECIFIC_DATETIME,
                TaskTemplateTrigger.TriggerType.RECURRING,
            ],
            is_enabled=True,
        )
        .select_related(
            "template",
        )
    )

    runs = []

    for trigger in triggers:
        if not scheduled_trigger_is_due(
            trigger,
            now,
        ):
            continue

        local_now = timezone.localtime(
            now
        )

        runs.append(
            run_task_template(
                trigger.template,
                trigger=trigger,
                occurrence_key=(
                    f"{local_now.date().isoformat()}-"
                    f"{trigger.pk}"
                ),
            )
        )

    return runs
