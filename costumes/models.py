from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from performance.models import ChoreographyPlan
from students.models import Student
from studios.models import Studio


class StudentMeasurementSet(models.Model):
    studio = models.ForeignKey(
        Studio,
        on_delete=models.CASCADE,
        related_name="student_measurement_sets",
    )

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="measurement_sets",
    )

    bust = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
    )

    waist = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
    )

    hips = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
    )

    girth = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
    )

    inseam = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
    )

    outseam = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
    )

    height = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
    )

    clothing_size = models.CharField(
        max_length=100,
        blank=True,
    )

    shoe_size = models.CharField(
        max_length=100,
        blank=True,
    )

    other_size_info = models.TextField(
        blank=True,
    )

    notes = models.TextField(
        blank=True,
    )

    measured_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="recorded_measurement_sets",
        null=True,
        blank=True,
    )

    measured_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    is_complete = models.BooleanField(
        default=False,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = [
            "-is_complete",
            "-measured_at",
            "-updated_at",
        ]

    def clean(self):
        super().clean()

        if (
            self.student_id
            and self.student.studio_id != self.studio_id
        ):
            raise ValidationError(
                {
                    "student": (
                        "Student and measurement set must belong "
                        "to the same studio."
                    )
                }
            )

    @property
    def has_measurements(self):
        measurement_values = [
            self.bust,
            self.waist,
            self.hips,
            self.girth,
            self.inseam,
            self.outseam,
            self.height,
            self.clothing_size,
            self.shoe_size,
            self.other_size_info,
            self.notes,
        ]

        return any(
            value not in {
                None,
                "",
            }
            for value in measurement_values
        )

    def mark_complete(
        self,
        user=None,
    ):
        self.is_complete = True
        self.measured_at = timezone.now()

        if user is not None:
            self.measured_by = user

        self.save(
            update_fields=[
                "is_complete",
                "measured_at",
                "measured_by",
                "updated_at",
            ]
        )

    def __str__(self):
        status = (
            "Complete"
            if self.is_complete
            else "In Progress"
        )

        return (
            f"{self.student} - "
            f"{status}"
        )


class Costume(models.Model):
    studio = models.ForeignKey(
        Studio,
        on_delete=models.CASCADE,
        related_name="costumes",
    )

    dance = models.ForeignKey(
        ChoreographyPlan,
        on_delete=models.CASCADE,
        related_name="costumes",
    )

    name = models.CharField(
        max_length=200,
    )

    student_notes = models.TextField(
        blank=True,
        help_text=(
            "Visible to assigned students and guardians."
        ),
    )

    internal_notes = models.TextField(
        blank=True,
        help_text=(
            "Visible only to studio staff."
        ),
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="created_costumes",
        null=True,
        blank=True,
    )

    is_active = models.BooleanField(
        default=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = [
            "dance__title",
            "name",
        ]

    def clean(self):
        super().clean()

        if (
            self.dance_id
            and self.dance.studio_id != self.studio_id
        ):
            raise ValidationError(
                {
                    "dance": (
                        "Dance and costume must belong "
                        "to the same studio."
                    )
                }
            )

    @property
    def class_instance(self):
        return self.dance.class_instance

    @property
    def front_image(self):
        return (
            self.images
            .filter(
                image_type=CostumeImage.ImageType.FRONT,
            )
            .order_by(
                "sort_order",
                "id",
            )
            .first()
        )

    def __str__(self):
        return (
            f"{self.dance} - "
            f"{self.name}"
        )


class CostumeImage(models.Model):
    class ImageType(models.TextChoices):
        FRONT = "front", "Front"
        BACK = "back", "Back"
        SHOES = "shoes", "Shoes"
        ACCESSORY = "accessory", "Accessory"
        OTHER = "other", "Other"

    costume = models.ForeignKey(
        Costume,
        on_delete=models.CASCADE,
        related_name="images",
    )

    image_type = models.CharField(
        max_length=20,
        choices=ImageType.choices,
    )

    image = models.ImageField(
        upload_to="costumes/",
    )

    caption = models.CharField(
        max_length=255,
        blank=True,
    )

    sort_order = models.PositiveIntegerField(
        default=0,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = [
            "image_type",
            "sort_order",
            "id",
        ]

    def __str__(self):
        return (
            f"{self.costume} - "
            f"{self.get_image_type_display()}"
        )


class CostumeLink(models.Model):
    costume = models.ForeignKey(
        Costume,
        on_delete=models.CASCADE,
        related_name="purchase_links",
    )

    label = models.CharField(
        max_length=150,
    )

    url = models.URLField()

    notes = models.CharField(
        max_length=255,
        blank=True,
    )

    sort_order = models.PositiveIntegerField(
        default=0,
    )

    class Meta:
        ordering = [
            "sort_order",
            "id",
        ]

    def __str__(self):
        return (
            f"{self.costume} - "
            f"{self.label}"
        )


class StudentCostumeAssignment(models.Model):
    class Status(models.TextChoices):
        NOT_STARTED = "not_started", "Not Started"
        MEASUREMENTS_READY = "measurements_ready", "Measurements Ready"
        ORDERED = "ordered", "Ordered"
        RECEIVED = "received", "Received"
        ALTERATIONS = "alterations", "Alterations Needed"
        READY = "ready", "Ready"
        DISTRIBUTED = "distributed", "Distributed"
        RETURNED = "returned", "Returned"

    costume = models.ForeignKey(
        Costume,
        on_delete=models.CASCADE,
        related_name="student_assignments",
    )

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="costume_assignments",
    )

    measurement_set_used = models.ForeignKey(
        StudentMeasurementSet,
        on_delete=models.SET_NULL,
        related_name="costume_assignments",
        null=True,
        blank=True,
    )

    costume_size = models.CharField(
        max_length=100,
        blank=True,
    )

    shoe_size = models.CharField(
        max_length=100,
        blank=True,
    )

    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.NOT_STARTED,
    )

    student_notes = models.TextField(
        blank=True,
    )

    internal_notes = models.TextField(
        blank=True,
    )

    is_active = models.BooleanField(
        default=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = [
            "student__last_name",
            "student__first_name",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "costume",
                    "student",
                ],
                name="unique_student_costume_assignment",
            )
        ]

    def clean(self):
        super().clean()

        if (
            self.student_id
            and self.costume_id
            and self.student.studio_id
            != self.costume.studio_id
        ):
            raise ValidationError(
                {
                    "student": (
                        "Student and costume must belong "
                        "to the same studio."
                    )
                }
            )

        if (
            self.measurement_set_used_id
            and self.measurement_set_used.student_id
            != self.student_id
        ):
            raise ValidationError(
                {
                    "measurement_set_used": (
                        "Measurement set must belong "
                        "to the assigned student."
                    )
                }
            )

    def __str__(self):
        return (
            f"{self.student} - "
            f"{self.costume}"
        )
