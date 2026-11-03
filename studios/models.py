from django.conf import settings
from django.db import models


class Studio(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)

    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)

    timezone = models.CharField(
        max_length=100,
        default="America/Detroit",
    )

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class StudioMembership(models.Model):
    class Role(models.TextChoices):
        ADMINISTRATOR = "administrator", "Administrator"
        TEACHER = "teacher", "Teacher"
        FAMILY = "family", "Family / Guardian"
        STUDENT = "student", "Student"

    class TourStatus(models.TextChoices):
        NOT_STARTED = "not_started", "Not Started"
        IN_PROGRESS = "in_progress", "In Progress"
        SKIPPED = "skipped", "Skipped"
        COMPLETED = "completed", "Completed"

    studio = models.ForeignKey(
        Studio,
        on_delete=models.CASCADE,
        related_name="memberships",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="studio_memberships",
    )

    role = models.CharField(
        max_length=30,
        choices=Role.choices,
    )

    is_active = models.BooleanField(default=True)

    # Existing memberships default to completed so the welcome tour only
    # appears automatically for newly-created studio owners. New paid studio
    # registrations explicitly set this to NOT_STARTED.
    onboarding_tour_status = models.CharField(
        max_length=20,
        choices=TourStatus.choices,
        default=TourStatus.COMPLETED,
    )
    onboarding_tour_step = models.PositiveSmallIntegerField(default=0)

    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["studio", "user", "role"],
                name="unique_studio_user_role",
            )
        ]

    def __str__(self):
        return f"{self.user} - {self.studio} - {self.get_role_display()}"


class StudioLocation(models.Model):
    studio = models.ForeignKey(
        Studio,
        on_delete=models.CASCADE,
        related_name="locations",
    )

    name = models.CharField(max_length=255)

    address_line_1 = models.CharField(max_length=255)
    address_line_2 = models.CharField(
        max_length=255,
        blank=True,
    )

    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)
    country = models.CharField(
        max_length=100,
        default="United States",
    )

    phone = models.CharField(max_length=50, blank=True)

    is_primary = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.studio.name} - {self.name}"


class StudioRoom(models.Model):
    studio = models.ForeignKey(
        Studio,
        on_delete=models.CASCADE,
        related_name="rooms",
    )

    location = models.ForeignKey(
        StudioLocation,
        on_delete=models.CASCADE,
        related_name="rooms",
        null=True,
        blank=True,
    )

    name = models.CharField(max_length=255)

    capacity = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    notes = models.TextField(blank=True)

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = [
            "name",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "studio",
                    "location",
                    "name",
                ],
                name="unique_room_name_per_location",
            )
        ]

    def clean(self):
        super().clean()

        if (
            self.location_id
            and self.studio_id
            and self.location.studio_id
            != self.studio_id
        ):
            from django.core.exceptions import ValidationError

            raise ValidationError(
                {
                    "location": (
                        "Room location must belong to the same studio."
                    )
                }
            )

    def __str__(self):
        if self.location:
            return f"{self.location.name} - {self.name}"

        return f"{self.studio.name} - {self.name}"


class StudioSettings(models.Model):
    studio = models.OneToOneField(
        Studio,
        on_delete=models.CASCADE,
        related_name="settings",
    )

    allow_online_registration = models.BooleanField(default=True)

    require_guardian_for_minors = models.BooleanField(default=True)

    evaluation_enabled = models.BooleanField(default=False)

    evaluation_frequency_days = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    allow_drop_ins_default = models.BooleanField(default=False)

    dashboard_customization_enabled = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    logo = models.ImageField(
        upload_to="studio_branding/",
        null=True,
        blank=True,
    )

    primary_color = models.CharField(
        max_length=7,
        default="#1663FF",
    )

    accent_color = models.CharField(
        max_length=7,
        default="#0197FC",
    )

    parent_sidebar_color = models.CharField(max_length=7, default="#FFFFFF")
    parent_logo_header_color = models.CharField(max_length=7, default="#E9EFFF")

    public_registration_enabled = models.BooleanField(
        default=True,
    )

    show_capacity_publicly = models.BooleanField(
        default=True,
    )

    allow_waitlist_requests = models.BooleanField(
        default=True,
    )

    class MeasurementUnit(models.TextChoices):
        INCHES = "in", "Inches"
        CENTIMETERS = "cm", "Centimeters"

    measurement_unit = models.CharField(
        max_length=4,
        choices=MeasurementUnit.choices,
        default=MeasurementUnit.INCHES,
    )

    remeasurement_interval_months = models.PositiveIntegerField(
        default=6,
        help_text="How many months a completed measurement stays current.",
    )

    public_widget_settings = models.JSONField(
        default=dict,
        blank=True,
    )

    def __str__(self):
        return f"{self.studio.name} Settings"


class DataImportJob(models.Model):
    class Status(models.TextChoices):
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        COMPLETED_WITH_ISSUES = "completed_with_issues", "Completed with issues"
        FAILED = "failed", "Failed"
        REVERTED = "reverted", "Reverted"

    studio = models.ForeignKey(
        Studio,
        on_delete=models.CASCADE,
        related_name="data_import_jobs",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="encore_data_import_jobs",
        null=True,
        blank=True,
    )
    import_type = models.CharField(max_length=50)
    original_filename = models.CharField(max_length=255)
    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.PROCESSING,
    )
    total_rows = models.PositiveIntegerField(default=0)
    created_count = models.PositiveIntegerField(default=0)
    updated_count = models.PositiveIntegerField(default=0)
    skipped_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    rejected_file = models.FileField(
        upload_to="import_reports/%Y/%m/",
        blank=True,
    )
    failure_message = models.TextField(blank=True)
    reverted_at = models.DateTimeField(null=True, blank=True)
    reverted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="encore_reverted_data_import_jobs",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def not_imported_count(self):
        return self.skipped_count + self.error_count + self.failed_count

    def __str__(self):
        return f"{self.studio.name} - {self.original_filename} ({self.get_status_display()})"


class DataImportRowResult(models.Model):
    class Status(models.TextChoices):
        CREATED = "created", "Created"
        UPDATED = "updated", "Updated"
        SKIPPED = "skipped", "Skipped"
        ERROR = "error", "Validation Error"
        FAILED = "failed", "Failed During Import"
        REVERTED = "reverted", "Reverted"
        REVERT_BLOCKED = "revert_blocked", "Revert Blocked"

    job = models.ForeignKey(
        DataImportJob,
        on_delete=models.CASCADE,
        related_name="row_results",
    )
    row_number = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=Status.choices)
    label = models.CharField(max_length=255, blank=True)
    reason = models.TextField(blank=True)
    source_data = models.JSONField(default=dict, blank=True)
    normalized_data = models.JSONField(default=dict, blank=True)
    object_type = models.CharField(max_length=100, blank=True)
    object_id = models.CharField(max_length=100, blank=True)
    was_created = models.BooleanField(default=False)
    before_data = models.JSONField(default=dict, blank=True)
    after_data = models.JSONField(default=dict, blank=True)
    revert_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["row_number", "id"]

    def __str__(self):
        return f"{self.job_id} row {self.row_number} - {self.get_status_display()}"


class VendorOnboardingRun(models.Model):
    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "In Progress"
        COMPLETED = "completed", "Completed"

    studio = models.ForeignKey(
        Studio,
        on_delete=models.CASCADE,
        related_name="vendor_onboarding_runs",
    )
    vendor = models.CharField(max_length=50)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.IN_PROGRESS,
    )
    step_state = models.JSONField(default=dict, blank=True)
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="encore_vendor_onboarding_runs",
        null=True,
        blank=True,
    )
    started_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["studio", "vendor"],
                name="unique_vendor_onboarding_per_studio",
            )
        ]

    def __str__(self):
        return f"{self.studio.name} - {self.vendor} onboarding"
