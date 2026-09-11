from django.core.exceptions import ValidationError
from django.db import models

from classes.models import Class
from instructors.models import Instructor
from studios.models import Studio


class ClassResource(models.Model):
    class ResourceType(models.TextChoices):
        MUSIC = "music", "Music"
        VIDEO = "video", "Video"
        DOCUMENT = "document", "Document"
        OTHER = "other", "Other"

    class Visibility(models.TextChoices):
        ENROLLED = "enrolled", "Enrolled Students & Families"
        STAFF = "staff", "Staff Only"

    studio = models.ForeignKey(
        Studio,
        on_delete=models.CASCADE,
        related_name="class_resources",
    )

    class_instance = models.ForeignKey(
        Class,
        on_delete=models.CASCADE,
        related_name="resources",
    )

    uploaded_by = models.ForeignKey(
        Instructor,
        on_delete=models.SET_NULL,
        related_name="uploaded_resources",
        null=True,
        blank=True,
    )

    resource_type = models.CharField(
        max_length=20,
        choices=ResourceType.choices,
        default=ResourceType.MUSIC,
    )

    title = models.CharField(
        max_length=200,
    )

    artist = models.CharField(
        max_length=200,
        blank=True,
    )

    duration_seconds = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Duration in seconds. Used for music timing.",
    )

    description = models.TextField(
        blank=True,
    )

    file = models.FileField(
        upload_to="class_resources/%Y/%m/",
        null=True,
        blank=True,
    )

    external_url = models.URLField(
        blank=True,
        help_text=(
            "Use for YouTube, Vimeo, Google Drive, or another "
            "external resource link."
        ),
    )

    visibility = models.CharField(
        max_length=20,
        choices=Visibility.choices,
        default=Visibility.ENROLLED,
    )

    is_active = models.BooleanField(
        default=True,
    )

    sort_order = models.PositiveIntegerField(
        default=0,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = [
            "class_instance__name",
            "sort_order",
            "-created_at",
        ]

    def clean(self):
        super().clean()

        if (
            self.class_instance_id
            and self.class_instance.studio_id != self.studio_id
        ):
            raise ValidationError(
                {
                    "class_instance": (
                        "Class must belong to the same studio."
                    )
                }
            )

        if (
            self.uploaded_by_id
            and self.uploaded_by.studio_id != self.studio_id
        ):
            raise ValidationError(
                {
                    "uploaded_by": (
                        "Instructor must belong to the same studio."
                    )
                }
            )

        if not self.file and not self.external_url:
            raise ValidationError(
                "Add either a file or an external URL."
            )

        if self.file and self.external_url:
            raise ValidationError(
                "Use either a file or an external URL, not both."
            )

        if (
            self.resource_type == self.ResourceType.VIDEO
            and not self.external_url
        ):
            raise ValidationError(
                {
                    "external_url": (
                        "Video resources should use an external link."
                    )
                }
            )

    @property
    def is_downloadable(self):
        return bool(self.file)

    def __str__(self):
        return f"{self.class_instance} - {self.title}"
