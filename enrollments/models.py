from django.core.exceptions import ValidationError
from django.db import models

from classes.models import Class
from students.models import Student


class Enrollment(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        WAITLISTED = "waitlisted", "Waitlisted"
        DROPPED = "dropped", "Dropped"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    class Source(models.TextChoices):
        ADMIN = "admin", "Admin"
        ONLINE = "online", "Online Registration"
        IMPORT = "import", "Imported"
        OTHER = "other", "Other"

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="enrollments",
    )

    class_instance = models.ForeignKey(
        Class,
        on_delete=models.CASCADE,
        related_name="enrollments",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )

    source = models.CharField(
        max_length=20,
        choices=Source.choices,
        default=Source.ADMIN,
    )

    tuition_override = models.DecimalField(
        max_digits=9,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=(
            "Optional student-specific tuition amount. "
            "Leave blank to use the class tuition amount."
        ),
    )

    enrolled_at = models.DateTimeField(auto_now_add=True)

    dropped_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    waitlisted_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = [
            "class_instance__name",
            "student__last_name",
            "student__first_name",
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "class_instance"],
                name="unique_student_class_enrollment",
            )
        ]

    def clean(self):
        super().clean()

        if self.student_id and self.class_instance_id:
            if self.student.studio_id != self.class_instance.studio_id:
                raise ValidationError(
                    {
                        "student": (
                            "The student and class must belong to the same studio."
                        )
                    }
                )

        if self.student_id and self.student.enrollment_blocked:
            raise ValidationError(
                {
                    "student": (
                        "This student is currently blocked from enrollment."
                    )
                }
            )

        if self.status == self.Status.ACTIVE and self.class_instance_id:
            active_qs = Enrollment.objects.filter(
                class_instance=self.class_instance,
                status=self.Status.ACTIVE,
            )

            if self.pk:
                active_qs = active_qs.exclude(pk=self.pk)

            if active_qs.count() >= self.class_instance.capacity:
                raise ValidationError(
                    {
                        "status": (
                            "This class is full. "
                            "Set the enrollment to Waitlisted instead."
                        )
                    }
                )

        if (
            self.class_instance_id
            and not self.class_instance.registration_open
            and self.status == self.Status.ACTIVE
        ):
            raise ValidationError(
                {
                    "class_instance": (
                        "Registration is currently closed for this class."
                    )
                }
            )

        if (
            self.class_instance_id
            and not self.class_instance.is_active
            and self.status == self.Status.ACTIVE
        ):
            raise ValidationError(
                {
                    "class_instance": (
                        "Students cannot be actively enrolled in an inactive class."
                    )
                }
            )

    @property
    def tuition_amount(self):
        if self.tuition_override is not None:
            return self.tuition_override

        return self.class_instance.tuition_amount

    def __str__(self):
        return (
            f"{self.student.first_name} {self.student.last_name} - "
            f"{self.class_instance.name}"
        )
