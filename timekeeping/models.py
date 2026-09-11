from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from studios.models import Studio


class ExtraWorkEntry(models.Model):
    class Category(models.TextChoices):
        TECH = "tech", "Tech / Production"
        ADMIN = "admin", "Administrative"
        REHEARSAL = "rehearsal", "Rehearsal"
        COSTUME = "costume", "Costume"
        EVENT = "event", "Event / Performance"
        MEETING = "meeting", "Meeting"
        TRAINING = "training", "Training"
        OTHER = "other", "Other"

    studio = models.ForeignKey(
        Studio,
        on_delete=models.CASCADE,
        related_name="extra_work_entries",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="extra_work_entries",
    )

    work_date = models.DateField()

    category = models.CharField(
        max_length=30,
        choices=Category.choices,
        default=Category.TECH,
    )

    duration_minutes = models.PositiveIntegerField()

    description = models.CharField(
        max_length=255,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = [
            "-work_date",
            "-created_at",
        ]

    def clean(self):
        super().clean()

        if (
            self.duration_minutes is not None
            and self.duration_minutes <= 0
        ):
            raise ValidationError(
                {
                    "duration_minutes": (
                        "Extra work time must be greater than zero."
                    )
                }
            )

    @property
    def duration_display(self):
        hours, minutes = divmod(
            self.duration_minutes,
            60,
        )

        if hours and minutes:
            return f"{hours}h {minutes}m"

        if hours:
            return f"{hours}h"

        return f"{minutes}m"

    def __str__(self):
        return (
            f"{self.user} - "
            f"{self.get_category_display()} - "
            f"{self.work_date}"
        )
