from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from classes.models import Class
from students.models import Student
from studios.models import Studio


class Task(models.Model):
    class Priority(models.TextChoices):
        LOW = "low", "Low"
        NORMAL = "normal", "Normal"
        HIGH = "high", "High"
        URGENT = "urgent", "Urgent"

    class AssignmentType(models.TextChoices):
        SELF = "self", "My Task"
        USER = "user", "Selected User"
        ALL_TEACHERS = "all_teachers", "All Teachers"

    class ContextType(models.TextChoices):
        PERSONAL = "personal", "Personal"
        CLASS = "class", "Class"
        STUDENT = "student", "Student"
        ADMIN = "admin", "Admin / Studio"

    class AudienceType(models.TextChoices):
        SELF = "self", "Myself"
        ADMIN = "admin", "Administrator"
        SELECTED_TEACHERS = "selected_teachers", "Selected Teachers"
        ALL_TEACHERS = "all_teachers", "All Teachers"
        CLASS_STAFF = "class_staff", "Class Staff"
        SELECTED_STUDENTS = "selected_students", "Selected Students"
        ALL_STUDENTS_IN_CLASS = "all_students_in_class", "All Students in Class"
        RELATED_STUDENT = "related_student", "Related / Triggering Student"

    class ApprovalStatus(models.TextChoices):
        NOT_REQUIRED = "not_required", "Not Required"
        PENDING = "pending", "Pending Admin Approval"
        APPROVED = "approved", "Approved"
        DENIED = "denied", "Denied"

    studio = models.ForeignKey(Studio, on_delete=models.CASCADE, related_name="tasks")
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.NORMAL)
    due_date = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="created_encore_tasks",
        null=True,
        blank=True,
    )

    context_type = models.CharField(
        max_length=30,
        choices=ContextType.choices,
        default=ContextType.PERSONAL,
    )

    audience_type = models.CharField(
        max_length=40,
        choices=AudienceType.choices,
        default=AudienceType.SELF,
    )

    approval_status = models.CharField(
        max_length=30,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.NOT_REQUIRED,
    )

    approval_requested_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="approved_encore_tasks",
        null=True,
        blank=True,
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    denied_at = models.DateTimeField(null=True, blank=True)
    approval_note = models.TextField(blank=True)

    class_instance = models.ForeignKey(
        Class,
        on_delete=models.CASCADE,
        related_name="tasks",
        null=True,
        blank=True,
    )

    # Related student/context only. Actual student recipients live in TaskAssignment.
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="tasks",
        null=True,
        blank=True,
    )

    is_student_facing = models.BooleanField(default=False)
    notify_assignees = models.BooleanField(default=True)

    source_template = models.ForeignKey(
        "TaskTemplate",
        on_delete=models.SET_NULL,
        related_name="generated_tasks",
        null=True,
        blank=True,
    )

    source_template_run = models.ForeignKey(
        "TaskTemplateRun",
        on_delete=models.SET_NULL,
        related_name="generated_tasks",
        null=True,
        blank=True,
    )

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Legacy compatibility fields.
    assignment_type = models.CharField(
        max_length=30,
        choices=AssignmentType.choices,
        default=AssignmentType.SELF,
    )

    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="assigned_encore_tasks",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["due_date", "-created_at"]

    def clean(self):
        super().clean()

        if self.class_instance_id and self.class_instance.studio_id != self.studio_id:
            raise ValidationError({"class_instance": "Class must belong to the same studio."})

        if self.student_id and self.student.studio_id != self.studio_id:
            raise ValidationError({"student": "Student must belong to the same studio."})

        if (
            self.student_id
            and self.class_instance_id
            and not self.student.enrollments.filter(class_instance=self.class_instance).exists()
        ):
            raise ValidationError(
                {"student": "Related student must be enrolled in the selected class."}
            )

        if (
            self.is_student_facing
            and self.audience_type
            not in {
                self.AudienceType.SELECTED_STUDENTS,
                self.AudienceType.ALL_STUDENTS_IN_CLASS,
                self.AudienceType.RELATED_STUDENT,
            }
        ):
            raise ValidationError(
                {"audience_type": "Student-facing tasks must target students."}
            )

    @property
    def is_overdue(self):
        return self.due_date is not None and self.due_date < timezone.localdate()

    def __str__(self):
        return self.title


class TaskAssignment(models.Model):
    class RecipientType(models.TextChoices):
        USER = "user", "User"
        STUDENT = "student", "Student"

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="assignments")
    recipient_type = models.CharField(max_length=20, choices=RecipientType.choices)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="encore_task_assignments",
        null=True,
        blank=True,
    )

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="task_assignments",
        null=True,
        blank=True,
    )

    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="completed_encore_assignments",
        null=True,
        blank=True,
    )
    reopened_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["task", "user"],
                condition=models.Q(recipient_type="user"),
                name="unique_task_user_assignment",
            ),
            models.UniqueConstraint(
                fields=["task", "student"],
                condition=models.Q(recipient_type="student"),
                name="unique_task_student_assignment",
            ),
        ]

    def clean(self):
        super().clean()

        if self.recipient_type == self.RecipientType.USER and not self.user_id:
            raise ValidationError({"user": "User assignment requires a user."})

        if self.recipient_type == self.RecipientType.STUDENT and not self.student_id:
            raise ValidationError({"student": "Student assignment requires a student."})

        if (
            self.user_id
            and not self.user.studio_memberships.filter(
                studio=self.task.studio,
                is_active=True,
            ).exists()
        ):
            raise ValidationError({"user": "Assigned user must have access to this studio."})

        if self.student_id and self.student.studio_id != self.task.studio_id:
            raise ValidationError({"student": "Assigned student must belong to this studio."})

    @property
    def is_complete(self):
        return self.completed_at is not None

    def complete(self, user):
        self.completed_at = timezone.now()
        self.completed_by = user
        self.reopened_at = None
        self.save(update_fields=["completed_at", "completed_by", "reopened_at"])

    def reopen(self):
        self.completed_at = None
        self.completed_by = None
        self.reopened_at = timezone.now()
        self.save(update_fields=["completed_at", "completed_by", "reopened_at"])

    def __str__(self):
        recipient = self.user if self.user_id else self.student
        return f"{self.task} → {recipient}"


class TaskCompletion(models.Model):
    """Legacy compatibility table during Task V2 rollout."""

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="completions")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="task_completions",
    )
    completed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["task", "user"],
                name="unique_task_completion_per_user",
            )
        ]

    def __str__(self):
        return f"{self.task} - {self.user}"


class TaskNotification(models.Model):
    class Kind(models.TextChoices):
        ASSIGNED = "assigned", "Task Assigned"
        TEMPLATE = "template", "Template Tasks Assigned"
        APPROVAL = "approval", "Task Approval Requested"
        APPROVED = "approved", "Task Approved"
        DENIED = "denied", "Task Denied"

    studio = models.ForeignKey(Studio, on_delete=models.CASCADE, related_name="task_notifications")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="encore_task_notifications",
    )
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name="notifications",
        null=True,
        blank=True,
    )
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.ASSIGNED)
    title = models.CharField(max_length=200)
    message = models.TextField(blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def is_read(self):
        return self.read_at is not None

    def __str__(self):
        return f"{self.user}: {self.title}"


class TaskTemplate(models.Model):
    class Visibility(models.TextChoices):
        PRIVATE = "private", "Private"
        STUDIO = "studio", "Studio Shared"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        PAUSED = "paused", "Paused"
        ARCHIVED = "archived", "Archived"

    studio = models.ForeignKey(Studio, on_delete=models.CASCADE, related_name="task_templates")
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_task_templates",
    )
    visibility = models.CharField(
        max_length=20,
        choices=Visibility.choices,
        default=Visibility.PRIVATE,
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class TaskTemplateItem(models.Model):
    class DueRule(models.TextChoices):
        NONE = "none", "No Due Date"
        SAME_DAY = "same_day", "Same Day"
        DAYS_AFTER = "days_after", "Days After Trigger"
        DAYS_BEFORE = "days_before", "Days Before Related Date"

    template = models.ForeignKey(TaskTemplate, on_delete=models.CASCADE, related_name="items")
    order = models.PositiveIntegerField(default=1)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    context_type = models.CharField(
        max_length=30,
        choices=Task.ContextType.choices,
        default=Task.ContextType.PERSONAL,
    )
    audience_type = models.CharField(
        max_length=40,
        choices=Task.AudienceType.choices,
        default=Task.AudienceType.SELF,
    )
    priority = models.CharField(
        max_length=20,
        choices=Task.Priority.choices,
        default=Task.Priority.NORMAL,
    )
    due_rule = models.CharField(
        max_length=20,
        choices=DueRule.choices,
        default=DueRule.NONE,
    )
    due_offset_days = models.IntegerField(default=0)
    due_time = models.TimeField(null=True, blank=True)
    assignment_config = models.JSONField(default=dict, blank=True)
    notify_assignees = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.template}: {self.title}"


class TaskTemplateTrigger(models.Model):
    class TriggerType(models.TextChoices):
        MANUAL = "manual", "Manual Run"
        NEW_CLASS = "new_class", "New Class Created"
        NEW_STUDENT = "new_student", "New Student Added"
        NEW_INSTRUCTOR = "new_instructor", "New Instructor Added"
        NEW_ENROLLMENT = "new_enrollment", "New Enrollment Created"
        SPECIFIC_DATETIME = "specific_datetime", "Specific Date / Time"
        RECURRING = "recurring", "Recurring Schedule"

    template = models.ForeignKey(TaskTemplate, on_delete=models.CASCADE, related_name="triggers")
    trigger_type = models.CharField(
        max_length=30,
        choices=TriggerType.choices,
        default=TriggerType.MANUAL,
    )
    configuration = models.JSONField(default=dict, blank=True)
    is_enabled = models.BooleanField(default=True)
    next_run_at = models.DateTimeField(null=True, blank=True)
    last_run_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.template} - {self.get_trigger_type_display()}"


class TaskTemplateRun(models.Model):
    class Status(models.TextChoices):
        STARTED = "started", "Started"
        COMPLETE = "complete", "Complete"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped"

    template = models.ForeignKey(TaskTemplate, on_delete=models.CASCADE, related_name="runs")
    trigger = models.ForeignKey(
        TaskTemplateTrigger,
        on_delete=models.SET_NULL,
        related_name="runs",
        null=True,
        blank=True,
    )
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="started_task_template_runs",
        null=True,
        blank=True,
    )

    target_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    target_object_id = models.PositiveBigIntegerField(null=True, blank=True)
    target_object = GenericForeignKey("target_content_type", "target_object_id")
    target_label = models.CharField(max_length=255, blank=True)

    idempotency_key = models.CharField(max_length=255, unique=True)
    occurrence_key = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.STARTED)
    tasks_created_count = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.template} - {self.started_at:%Y-%m-%d %H:%M}"
