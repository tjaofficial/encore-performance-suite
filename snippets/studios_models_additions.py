
from django.conf import settings
from django.db import models

# Keep your existing Studio, StudioMembership, StudioLocation, StudioRoom, StudioSettings models above.
# Add the following models at the end of studios/models.py if they are not already present.

class DataImportJob(models.Model):
    class Status(models.TextChoices):
        COMPLETED = "completed", "Completed"
        COMPLETED_WITH_ISSUES = "completed_with_issues", "Completed with issues"
        UNDONE = "undone", "Undone"

    studio = models.ForeignKey(
        "studios.Studio",
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
    filename = models.CharField(max_length=255)
    import_type = models.CharField(max_length=50)
    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.COMPLETED,
    )
    total_rows = models.PositiveIntegerField(default=0)
    created_count = models.PositiveIntegerField(default=0)
    updated_count = models.PositiveIntegerField(default=0)
    skipped_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    not_imported_csv = models.TextField(blank=True)
    undone_at = models.DateTimeField(null=True, blank=True)
    undone_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="encore_undone_data_import_jobs",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.studio} - {self.filename} - {self.created_at:%Y-%m-%d %H:%M}"


class DataImportRowResult(models.Model):
    class Result(models.TextChoices):
        CREATED = "created", "Created"
        UPDATED = "updated", "Updated"
        SKIPPED = "skipped", "Skipped"
        ERROR = "error", "Error"
        FAILED = "failed", "Failed"
        UNDONE = "undone", "Undone"
        UNDO_BLOCKED = "undo_blocked", "Undo blocked"

    job = models.ForeignKey(
        DataImportJob,
        on_delete=models.CASCADE,
        related_name="row_results",
    )
    row_number = models.PositiveIntegerField()
    label = models.CharField(max_length=255, blank=True)
    result = models.CharField(max_length=20, choices=Result.choices)
    reason = models.TextField(blank=True)

    source_row = models.JSONField(default=dict, blank=True)
    normalized = models.JSONField(default=dict, blank=True)

    model_label = models.CharField(max_length=100, blank=True)
    object_pk = models.CharField(max_length=100, blank=True)

    before_snapshot = models.JSONField(default=dict, blank=True)
    after_snapshot = models.JSONField(default=dict, blank=True)

    undo_message = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["row_number", "id"]

    def __str__(self):
        return f"{self.job_id} row {self.row_number} - {self.result}"
