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


class Vendor(models.Model):
    studio = models.ForeignKey(
        Studio,
        on_delete=models.CASCADE,
        related_name="costume_vendors",
    )
    name = models.CharField(max_length=200)
    abbreviation = models.CharField(max_length=50, blank=True)
    contact_name = models.CharField(max_length=200, blank=True)
    address_line_1 = models.CharField(max_length=255, blank=True)
    address_line_2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=120, blank=True)
    state = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=30, blank=True)
    phone = models.CharField(max_length=60, blank=True)
    fax = models.CharField(max_length=60, blank=True)
    email = models.EmailField(blank=True)
    customer_number = models.CharField(max_length=100, blank=True)
    website = models.URLField(blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["studio", "name"],
                name="unique_costume_vendor_name_per_studio",
            )
        ]

    def __str__(self):
        return self.name


class VendorSizeChart(models.Model):
    class Gender(models.TextChoices):
        ALL = "all", "All"
        FEMALE = "female", "Female"
        MALE = "male", "Male"

    vendor = models.ForeignKey(
        Vendor,
        on_delete=models.CASCADE,
        related_name="size_charts",
    )
    name = models.CharField(max_length=150)
    gender = models.CharField(
        max_length=20,
        choices=Gender.choices,
        default=Gender.ALL,
    )
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["vendor", "name"],
                name="unique_vendor_size_chart_name",
            )
        ]

    def __str__(self):
        return f"{self.vendor.name} — {self.name}"


class VendorSizeEntry(models.Model):
    chart = models.ForeignKey(
        VendorSizeChart,
        on_delete=models.CASCADE,
        related_name="entries",
    )
    size_label = models.CharField(max_length=100)
    sort_order = models.PositiveIntegerField(default=0)

    bust_min = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    bust_max = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    waist_min = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    waist_max = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    hips_min = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    hips_max = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    girth_min = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    girth_max = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    inseam_min = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    inseam_max = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    outseam_min = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    outseam_max = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    height_min = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    height_max = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    age_min = models.PositiveIntegerField(null=True, blank=True)
    age_max = models.PositiveIntegerField(null=True, blank=True)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"{self.chart} — {self.size_label}"


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

    class GenderScope(models.TextChoices):
        ALL = "all", "All"
        FEMALE = "female", "Female"
        MALE = "male", "Male"

    gender_scope = models.CharField(
        max_length=20,
        choices=GenderScope.choices,
        default=GenderScope.ALL,
    )

    vendor = models.ForeignKey(
        Vendor,
        on_delete=models.SET_NULL,
        related_name="costumes",
        null=True,
        blank=True,
    )

    vendor_size_chart = models.ForeignKey(
        VendorSizeChart,
        on_delete=models.SET_NULL,
        related_name="costumes",
        null=True,
        blank=True,
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

        if (
            self.vendor_id
            and self.vendor.studio_id != self.studio_id
        ):
            raise ValidationError({"vendor": "Vendor must belong to the same studio."})

        if self.vendor_size_chart_id:
            if not self.vendor_id:
                raise ValidationError({"vendor_size_chart": "Select a vendor first."})
            if self.vendor_size_chart.vendor_id != self.vendor_id:
                raise ValidationError({"vendor_size_chart": "Size chart must belong to the selected vendor."})

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
