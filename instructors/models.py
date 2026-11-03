import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from studios.models import Studio


class Instructor(models.Model):
    studio = models.ForeignKey(
        Studio,
        on_delete=models.CASCADE,
        related_name="instructors",
    )

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="instructor_profile",
        null=True,
        blank=True,
    )

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)

    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)

    address_line_1 = models.CharField(max_length=255, blank=True)
    address_line_2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)

    emergency_contact_name = models.CharField(max_length=255, blank=True)
    emergency_contact_phone = models.CharField(max_length=50, blank=True)
    emergency_contact_relationship = models.CharField(max_length=100, blank=True)

    bio = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    activation_token = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
    )
    activation_sent_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    activation_expires_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    claimed_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    profile_verified_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    availability_completed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def activation_status(self):
        if self.claimed_at and self.user_id:
            return "claimed"
        if self.activation_sent_at:
            return "invite_sent"
        if not self.email:
            return "missing_email"
        if self.is_active:
            return "active_unclaimed"
        return "needs_activation"

    def __str__(self):
        return self.full_name


class InstructorAvailability(models.Model):
    class DayOfWeek(models.IntegerChoices):
        MONDAY = 0, "Monday"
        TUESDAY = 1, "Tuesday"
        WEDNESDAY = 2, "Wednesday"
        THURSDAY = 3, "Thursday"
        FRIDAY = 4, "Friday"
        SATURDAY = 5, "Saturday"
        SUNDAY = 6, "Sunday"

    instructor = models.ForeignKey(
        Instructor,
        on_delete=models.CASCADE,
        related_name="availability",
    )

    day_of_week = models.PositiveSmallIntegerField(
        choices=DayOfWeek.choices,
    )

    start_time = models.TimeField()
    end_time = models.TimeField()
    is_available = models.BooleanField(default=True)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["day_of_week", "start_time"]
        constraints = [
            models.UniqueConstraint(
                fields=["instructor", "day_of_week", "start_time", "end_time"],
                name="unique_instructor_availability_window",
            )
        ]

    def __str__(self):
        return (
            f"{self.instructor.full_name} - "
            f"{self.get_day_of_week_display()} "
            f"{self.start_time}-{self.end_time}"
        )


class PayrollSettings(models.Model):
    class PayPeriodFrequency(models.TextChoices):
        WEEKLY = "weekly", "Weekly"
        BIWEEKLY = "biweekly", "Biweekly"
        SEMIMONTHLY = "semimonthly", "Semi-Monthly"
        MONTHLY = "monthly", "Monthly"

    class RoundingMinutes(models.IntegerChoices):
        EXACT = 0, "Exact Time"
        FIVE = 5, "Nearest 5 Minutes"
        TEN = 10, "Nearest 10 Minutes"
        FIFTEEN = 15, "Nearest 15 Minutes"

    studio = models.OneToOneField(
        Studio,
        on_delete=models.CASCADE,
        related_name="payroll_settings",
    )

    pay_period_frequency = models.CharField(
        max_length=20,
        choices=PayPeriodFrequency.choices,
        default=PayPeriodFrequency.BIWEEKLY,
    )

    pay_period_anchor_date = models.DateField(
        null=True,
        blank=True,
        help_text=(
            "A known first day of a weekly or biweekly pay period. "
            "Monthly and semi-monthly schedules do not use this field."
        ),
    )

    minimum_session_minutes = models.PositiveIntegerField(
        default=60,
        help_text=(
            "Minimum payable minutes for a scheduled class occurrence."
        ),
    )

    rounding_minutes = models.PositiveSmallIntegerField(
        choices=RoundingMinutes.choices,
        default=RoundingMinutes.EXACT,
        help_text=(
            "How payable time above the minimum should be rounded."
        ),
    )

    extra_work_uses_regular_rate = models.BooleanField(
        default=True,
        help_text=(
            "Use the instructor's regular hourly rate for extra work unless "
            "an extra-work rate is stored on their compensation record."
        ),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        super().clean()

        if self.minimum_session_minutes < 1:
            raise ValidationError(
                {
                    "minimum_session_minutes": (
                        "Minimum payable session time must be at least 1 minute."
                    )
                }
            )

    def __str__(self):
        return f"{self.studio.name} Payroll Settings"


class InstructorCompensation(models.Model):
    class CompensationType(models.TextChoices):
        HOURLY = "hourly", "Hourly"
        SALARY = "salary", "Salary"

    class SalaryBasis(models.TextChoices):
        ANNUAL = "annual", "Annual"
        MONTHLY = "monthly", "Monthly"

    instructor = models.ForeignKey(
        Instructor,
        on_delete=models.CASCADE,
        related_name="compensation_records",
    )

    compensation_type = models.CharField(
        max_length=20,
        choices=CompensationType.choices,
        default=CompensationType.HOURLY,
    )

    hourly_rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )

    salary_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )

    salary_basis = models.CharField(
        max_length=20,
        choices=SalaryBasis.choices,
        blank=True,
    )

    extra_work_hourly_rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=(
            "Optional override rate for extra work. Leave blank to use "
            "the regular hourly rate when studio settings allow it."
        ),
    )

    effective_start = models.DateField()
    effective_end = models.DateField(
        null=True,
        blank=True,
    )

    notes = models.TextField(blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="created_compensation_records",
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = [
            "-effective_start",
            "-created_at",
        ]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "instructor",
                    "effective_start",
                ],
                name="unique_instructor_compensation_start",
            )
        ]

    def clean(self):
        super().clean()

        errors = {}

        if (
            self.effective_end
            and self.effective_end < self.effective_start
        ):
            errors["effective_end"] = (
                "Effective end date cannot be before the start date."
            )

        if self.compensation_type == self.CompensationType.HOURLY:
            if self.hourly_rate is None or self.hourly_rate <= 0:
                errors["hourly_rate"] = (
                    "Enter an hourly rate greater than $0."
                )

            self.salary_amount = None
            self.salary_basis = ""

        elif self.compensation_type == self.CompensationType.SALARY:
            if self.salary_amount is None or self.salary_amount <= 0:
                errors["salary_amount"] = (
                    "Enter a salary amount greater than $0."
                )

            if not self.salary_basis:
                errors["salary_basis"] = (
                    "Choose whether the salary amount is annual or monthly."
                )

            self.hourly_rate = None

        if (
            self.extra_work_hourly_rate is not None
            and self.extra_work_hourly_rate <= 0
        ):
            errors["extra_work_hourly_rate"] = (
                "Extra-work rate must be greater than $0."
            )

        if errors:
            raise ValidationError(errors)

    @property
    def rate_display(self):
        if self.compensation_type == self.CompensationType.HOURLY:
            if self.hourly_rate is None:
                return "Hourly · Rate not set"
            return f"${self.hourly_rate:,.2f}/hr"

        if self.salary_amount is None:
            return "Salary · Amount not set"

        suffix = (
            "/year"
            if self.salary_basis == self.SalaryBasis.ANNUAL
            else "/month"
        )
        return f"${self.salary_amount:,.2f}{suffix}"

    def __str__(self):
        return (
            f"{self.instructor.full_name} · "
            f"{self.get_compensation_type_display()} · "
            f"{self.effective_start}"
        )

