from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from classes.models import Class, ClassMeeting
from communications.models import EmailTemplate
from students.models import Student
from studios.models import Studio


class AttendanceSession(models.Model):
    class_instance = models.ForeignKey(
        Class,
        on_delete=models.CASCADE,
        related_name="attendance_sessions",
    )

    session_date = models.DateField()

    start_time = models.TimeField(
        null=True,
        blank=True,
        help_text="Optional override/reference time for this attendance session.",
    )

    notes = models.TextField(blank=True)

    taken_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="attendance_sessions_taken",
        null=True,
        blank=True,
    )

    is_finalized = models.BooleanField(
        default=False,
        help_text="Finalized sessions can later be treated as locked attendance.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-session_date", "class_instance__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["class_instance", "session_date", "start_time"],
                name="unique_attendance_session_per_class_date_time",
            )
        ]

    def __str__(self):
        return (
            f"{self.class_instance.class_id} - "
            f"{self.session_date}"
        )


class AttendanceAutomationTrigger(models.Model):
    class TriggerType(models.TextChoices):
        CONSECUTIVE_ABSENCES = "consecutive_absences", "Consecutive Absences"

    studio = models.ForeignKey(
        Studio,
        on_delete=models.CASCADE,
        related_name="attendance_automation_triggers",
    )
    name = models.CharField(max_length=160, default="Consecutive Absence Alert")
    trigger_type = models.CharField(
        max_length=40,
        choices=TriggerType.choices,
        default=TriggerType.CONSECUTIVE_ABSENCES,
    )
    threshold_value = models.PositiveSmallIntegerField(default=3)
    is_enabled = models.BooleanField(default=True)
    highlight_student = models.BooleanField(default=True)
    create_makeup_requirements = models.BooleanField(default=True)
    send_email = models.BooleanField(default=True)
    create_parent_task = models.BooleanField(default=True)
    notify_teacher = models.BooleanField(default=True)
    email_template = models.ForeignKey(
        EmailTemplate,
        on_delete=models.SET_NULL,
        related_name="attendance_automation_triggers",
        null=True,
        blank=True,
        limit_choices_to={"category": EmailTemplate.Category.ATTENDANCE},
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["threshold_value", "name"]

    def clean(self):
        super().clean()
        if self.threshold_value < 1:
            raise ValidationError({"threshold_value": "Threshold must be at least 1."})
        if self.email_template_id and self.email_template.studio_id != self.studio_id:
            raise ValidationError({"email_template": "Email template must belong to the same studio."})

    def __str__(self):
        return f"{self.studio.name} - {self.name} ({self.threshold_value})"


class MakeupRequirement(models.Model):
    class Status(models.TextChoices):
        OUTSTANDING = "outstanding", "Outstanding"
        COMPLETED = "completed", "Completed"
        WAIVED = "waived", "Waived"

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="makeup_requirements",
    )
    source_class = models.ForeignKey(
        Class,
        on_delete=models.CASCADE,
        related_name="makeup_requirements",
    )
    source_attendance_record = models.OneToOneField(
        "AttendanceRecord",
        on_delete=models.CASCADE,
        related_name="makeup_requirement",
        null=True,
        blank=True,
    )
    absence_request_session = models.OneToOneField(
        "AbsenceRequestSession",
        on_delete=models.SET_NULL,
        related_name="makeup_requirement",
        null=True,
        blank=True,
    )
    trigger = models.ForeignKey(
        AttendanceAutomationTrigger,
        on_delete=models.SET_NULL,
        related_name="makeup_requirements",
        null=True,
        blank=True,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OUTSTANDING,
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.student} - makeup for {self.source_class.class_id}"


class MakeupAssignment(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        COMPLETED = "completed", "Completed"
        MISSED = "missed", "Missed"
        CANCELLED = "cancelled", "Cancelled"

    requirement = models.ForeignKey(
        MakeupRequirement,
        on_delete=models.SET_NULL,
        related_name="assignments",
        null=True,
        blank=True,
    )
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="makeup_assignments",
    )
    source_class = models.ForeignKey(
        Class,
        on_delete=models.SET_NULL,
        related_name="makeup_students_sent",
        null=True,
        blank=True,
    )
    makeup_class = models.ForeignKey(
        Class,
        on_delete=models.CASCADE,
        related_name="makeup_students_received",
    )
    scheduled_date = models.DateField()
    makeup_meeting = models.ForeignKey(
        ClassMeeting, on_delete=models.SET_NULL, related_name="makeup_assignments",
        null=True, blank=True,
    )
    attendance_session = models.ForeignKey(
        AttendanceSession,
        on_delete=models.SET_NULL,
        related_name="makeup_assignments",
        null=True,
        blank=True,
    )
    attendance_record = models.OneToOneField(
        "AttendanceRecord",
        on_delete=models.SET_NULL,
        related_name="makeup_assignment_result",
        null=True,
        blank=True,
    )
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="makeup_assignments_added",
        null=True,
        blank=True,
    )
    is_walk_in = models.BooleanField(default=False)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.SCHEDULED,
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["scheduled_date", "student__last_name", "student__first_name"]

    def __str__(self):
        return f"{self.student} -> {self.makeup_class.class_id} on {self.scheduled_date}"


class AttendanceTriggerEvent(models.Model):
    trigger = models.ForeignKey(
        AttendanceAutomationTrigger,
        on_delete=models.CASCADE,
        related_name="events",
    )
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="attendance_trigger_events",
    )
    class_instance = models.ForeignKey(
        Class,
        on_delete=models.CASCADE,
        related_name="attendance_trigger_events",
    )
    attendance_record = models.ForeignKey(
        "AttendanceRecord",
        on_delete=models.CASCADE,
        related_name="trigger_events",
    )
    consecutive_count = models.PositiveSmallIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["trigger", "attendance_record"],
                name="unique_attendance_trigger_event_per_record",
            )
        ]

    def __str__(self):
        return f"{self.student} - {self.trigger.name} - {self.consecutive_count}"


class AttendanceRecord(models.Model):
    class Status(models.TextChoices):
        PRESENT = "present", "Present"
        ABSENT = "absent", "Absent"
        LATE = "late", "Late"
        EXCUSED = "excused", "Excused"
        LEFT_EARLY = "left_early", "Left Early"

    class Context(models.TextChoices):
        REGULAR = "regular", "Regular Class"
        MAKEUP = "makeup", "Makeup Class"

    session = models.ForeignKey(
        AttendanceSession,
        on_delete=models.CASCADE,
        related_name="records",
    )

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="attendance_records",
    )

    context = models.CharField(
        max_length=20,
        choices=Context.choices,
        default=Context.REGULAR,
    )

    makeup_assignment = models.OneToOneField(
        MakeupAssignment,
        on_delete=models.SET_NULL,
        related_name="attendance",
        null=True,
        blank=True,
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PRESENT,
    )

    arrival_time = models.TimeField(
        null=True,
        blank=True,
    )

    departure_time = models.TimeField(
        null=True,
        blank=True,
    )

    note = models.CharField(
        max_length=500,
        blank=True,
    )

    marked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="attendance_records_marked",
        null=True,
        blank=True,
    )

    marked_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = [
            "-session__session_date",
            "student__last_name",
            "student__first_name",
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["session", "student"],
                name="unique_student_attendance_per_session",
            )
        ]

    def clean(self):
        super().clean()

        if not self.session_id or not self.student_id:
            return

        class_instance = self.session.class_instance

        if self.student.studio_id != class_instance.studio_id:
            raise ValidationError(
                {
                    "student": (
                        "The student and attendance session must belong "
                        "to the same studio."
                    )
                }
            )

        if self.context == self.Context.MAKEUP:
            if (
                self.makeup_assignment_id
                and self.makeup_assignment.student_id != self.student_id
            ):
                raise ValidationError(
                    {
                        "makeup_assignment": (
                            "Makeup assignment student must match the attendance student."
                        )
                    }
                )
            return

        is_enrolled = self.student.enrollments.filter(
            class_instance=class_instance,
            status="active",
        ).exists()

        if not is_enrolled:
            raise ValidationError(
                {
                    "student": (
                        "This student is not actively enrolled in the class "
                        "for this attendance session."
                    )
                }
            )

    def __str__(self):
        return (
            f"{self.student.first_name} {self.student.last_name} - "
            f"{self.session.session_date} - "
            f"{self.get_status_display()}"
        )


class AttendancePolicy(models.Model):
    """Studio-specific permissions for makeup management."""
    studio = models.OneToOneField(Studio, on_delete=models.CASCADE, related_name="attendance_policy")
    teachers_can_assign_makeups = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.studio} attendance policy"


class MakeupEligibilityRule(models.Model):
    """An original class can be made up at one specific weekly class meeting."""
    studio = models.ForeignKey(Studio, on_delete=models.CASCADE, related_name="makeup_eligibility_rules")
    source_class = models.ForeignKey(Class, on_delete=models.CASCADE, related_name="makeup_eligibility_rules")
    eligible_meeting = models.ForeignKey(ClassMeeting, on_delete=models.CASCADE, related_name="makeup_eligibility_rules")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["source_class__name", "eligible_meeting__day_of_week", "eligible_meeting__start_time"]
        constraints = [models.UniqueConstraint(fields=["source_class", "eligible_meeting"], name="unique_makeup_eligible_meeting")]

    def clean(self):
        super().clean()
        if self.source_class_id and self.source_class.studio_id != self.studio_id:
            raise ValidationError({"source_class": "Original class must be part of this studio."})
        if self.eligible_meeting_id and self.eligible_meeting.class_instance.studio_id != self.studio_id:
            raise ValidationError({"eligible_meeting": "Make-up meeting must be part of this studio."})

    def __str__(self):
        return f"{self.source_class} -> {self.eligible_meeting}"


class AbsenceRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending Review"
        APPROVED = "approved", "Approved"
        DENIED = "denied", "Denied"

    studio = models.ForeignKey(Studio, on_delete=models.CASCADE, related_name="absence_requests")
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="submitted_absence_requests")
    reason = models.TextField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_absence_requests")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_comment = models.TextField(blank=True)
    require_makeups = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class AbsenceRequestSession(models.Model):
    request = models.ForeignKey(AbsenceRequest, on_delete=models.CASCADE, related_name="sessions")
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="requested_absences")
    class_instance = models.ForeignKey(Class, on_delete=models.CASCADE, related_name="requested_absences")
    meeting = models.ForeignKey(ClassMeeting, on_delete=models.PROTECT, related_name="requested_absences")
    session_date = models.DateField()

    class Meta:
        ordering = ["session_date", "class_instance__name"]
        constraints = [models.UniqueConstraint(fields=["request", "student", "meeting", "session_date"], name="unique_absence_request_session")]

    def clean(self):
        super().clean()
        if self.student_id and self.student.studio_id != self.request.studio_id:
            raise ValidationError("Student belongs to a different studio.")
        if self.class_instance_id and self.class_instance.studio_id != self.request.studio_id:
            raise ValidationError("Class belongs to a different studio.")
        if self.meeting_id and self.meeting.class_instance_id != self.class_instance_id:
            raise ValidationError("Meeting does not belong to the selected class.")
