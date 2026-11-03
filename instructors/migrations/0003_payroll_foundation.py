from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("instructors", "0002_instructor_activation"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PayrollSettings",
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
                (
                    "pay_period_frequency",
                    models.CharField(
                        choices=[
                            ("weekly", "Weekly"),
                            ("biweekly", "Biweekly"),
                            ("semimonthly", "Semi-Monthly"),
                            ("monthly", "Monthly"),
                        ],
                        default="biweekly",
                        max_length=20,
                    ),
                ),
                (
                    "minimum_session_minutes",
                    models.PositiveIntegerField(
                        default=60,
                        help_text=(
                            "Minimum payable minutes for a scheduled class occurrence."
                        ),
                    ),
                ),
                (
                    "rounding_minutes",
                    models.PositiveSmallIntegerField(
                        choices=[
                            (0, "Exact Time"),
                            (5, "Nearest 5 Minutes"),
                            (10, "Nearest 10 Minutes"),
                            (15, "Nearest 15 Minutes"),
                        ],
                        default=0,
                        help_text=(
                            "How payable time above the minimum should be rounded."
                        ),
                    ),
                ),
                (
                    "extra_work_uses_regular_rate",
                    models.BooleanField(
                        default=True,
                        help_text=(
                            "Use the instructor's regular hourly rate for extra work "
                            "unless an extra-work rate is stored on their compensation record."
                        ),
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True),
                ),
                (
                    "studio",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="payroll_settings",
                        to="studios.studio",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="InstructorCompensation",
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
                (
                    "compensation_type",
                    models.CharField(
                        choices=[
                            ("hourly", "Hourly"),
                            ("salary", "Salary"),
                        ],
                        default="hourly",
                        max_length=20,
                    ),
                ),
                (
                    "hourly_rate",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=10,
                        null=True,
                    ),
                ),
                (
                    "salary_amount",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=12,
                        null=True,
                    ),
                ),
                (
                    "salary_basis",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("annual", "Annual"),
                            ("monthly", "Monthly"),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    "extra_work_hourly_rate",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        help_text=(
                            "Optional override rate for extra work. Leave blank to use "
                            "the regular hourly rate when studio settings allow it."
                        ),
                        max_digits=10,
                        null=True,
                    ),
                ),
                (
                    "effective_start",
                    models.DateField(),
                ),
                (
                    "effective_end",
                    models.DateField(
                        blank=True,
                        null=True,
                    ),
                ),
                (
                    "notes",
                    models.TextField(blank=True),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_compensation_records",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "instructor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="compensation_records",
                        to="instructors.instructor",
                    ),
                ),
            ],
            options={
                "ordering": [
                    "-effective_start",
                    "-created_at",
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="instructorcompensation",
            constraint=models.UniqueConstraint(
                fields=("instructor", "effective_start"),
                name="unique_instructor_compensation_start",
            ),
        ),
    ]
