from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from classes.models import Class
from students.models import Student


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


class AttendanceRecord(models.Model):
    class Status(models.TextChoices):
        PRESENT = "present", "Present"
        ABSENT = "absent", "Absent"
        LATE = "late", "Late"
        EXCUSED = "excused", "Excused"
        LEFT_EARLY = "left_early", "Left Early"

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
