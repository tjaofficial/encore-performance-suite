import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("studios", "0005_studiosettings_public_widget_settings"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="DataImportJob",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("import_type", models.CharField(max_length=50)),
                ("original_filename", models.CharField(max_length=255)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("processing", "Processing"),
                            ("completed", "Completed"),
                            ("completed_with_issues", "Completed with issues"),
                            ("failed", "Failed"),
                            ("reverted", "Reverted"),
                        ],
                        default="processing",
                        max_length=30,
                    ),
                ),
                ("total_rows", models.PositiveIntegerField(default=0)),
                ("created_count", models.PositiveIntegerField(default=0)),
                ("updated_count", models.PositiveIntegerField(default=0)),
                ("skipped_count", models.PositiveIntegerField(default=0)),
                ("error_count", models.PositiveIntegerField(default=0)),
                ("failed_count", models.PositiveIntegerField(default=0)),
                (
                    "rejected_file",
                    models.FileField(
                        blank=True,
                        upload_to="import_reports/%Y/%m/",
                    ),
                ),
                ("failure_message", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "completed_at",
                    models.DateTimeField(
                        blank=True,
                        null=True,
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="encore_data_import_jobs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "studio",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="data_import_jobs",
                        to="studios.studio",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="DataImportRowResult",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("row_number", models.PositiveIntegerField()),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("created", "Created"),
                            ("updated", "Updated"),
                            ("skipped", "Skipped"),
                            ("error", "Validation Error"),
                            ("failed", "Failed During Import"),
                        ],
                        max_length=20,
                    ),
                ),
                ("label", models.CharField(blank=True, max_length=255)),
                ("reason", models.TextField(blank=True)),
                (
                    "source_data",
                    models.JSONField(
                        blank=True,
                        default=dict,
                    ),
                ),
                (
                    "normalized_data",
                    models.JSONField(
                        blank=True,
                        default=dict,
                    ),
                ),
                (
                    "object_type",
                    models.CharField(
                        blank=True,
                        max_length=100,
                    ),
                ),
                (
                    "object_id",
                    models.CharField(
                        blank=True,
                        max_length=100,
                    ),
                ),
                ("was_created", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "job",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="row_results",
                        to="studios.dataimportjob",
                    ),
                ),
            ],
            options={
                "ordering": ["row_number", "id"],
            },
        ),
    ]