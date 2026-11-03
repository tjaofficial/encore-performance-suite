from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Sum
from django.utils import timezone

from classes.models import Class, Season
from enrollments.models import Enrollment
from families.models import Family
from students.models import Student
from studios.models import Studio


class FamilyAccount(models.Model):
    studio = models.ForeignKey(
        Studio,
        on_delete=models.CASCADE,
        related_name="billing_accounts",
    )

    family = models.OneToOneField(
        Family,
        on_delete=models.CASCADE,
        related_name="billing_account",
    )

    autopay_enabled = models.BooleanField(default=False)
    statement_notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["family__family_name", "family_id"]

    def clean(self):
        super().clean()

        if (
            self.family_id
            and self.studio_id
            and self.family.studio_id != self.studio_id
        ):
            raise ValidationError(
                "FamilyAccount studio must match the Family studio."
            )

    @property
    def total_charges(self):
        return (
            self.charges
            .filter(
                status__in=[
                    Charge.Status.OPEN,
                    Charge.Status.PARTIALLY_PAID,
                    Charge.Status.PAID,
                ]
            )
            .aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )

    @property
    def total_payments(self):
        received = (self.payments.filter(status=Payment.Status.SUCCEEDED)
                    .aggregate(total=Sum("amount"))["total"] or Decimal("0.00"))
        refunded = (PaymentRefund.objects.filter(payment__account=self, status=PaymentRefund.Status.SUCCEEDED)
                    .aggregate(total=Sum("amount"))["total"] or Decimal("0.00"))
        return received - refunded

    @property
    def total_credits(self):
        return (
            self.credits
            .filter(is_void=False)
            .aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )

    @property
    def balance(self):
        open_balance = sum(
            (
                charge.balance_remaining
                for charge in self.charges.filter(
                    status__in=[
                        Charge.Status.OPEN,
                        Charge.Status.PARTIALLY_PAID,
                    ]
                )
            ),
            Decimal("0.00"),
        )

        unapplied_credit = sum(
            (
                credit.remaining_amount
                for credit in self.credits.filter(
                    is_void=False,
                )
            ),
            Decimal("0.00"),
        )

        return open_balance - unapplied_credit

    def __str__(self):
        return f"{self.family} Billing Account"


class TuitionPlan(models.Model):
    """
    Billing policy.

    IMPORTANT:
    TuitionPlan.amount is retained only for backward compatibility with
    early development data. Normal enrollment billing MUST use:
        Enrollment.tuition_override
        OR Class.tuition_amount

    The policy controls HOW/WHEN tuition is billed.
    """

    class BillingFrequency(models.TextChoices):
        ONE_TIME = "one_time", "One Time"
        WEEKLY = "weekly", "Weekly"
        MONTHLY = "monthly", "Monthly"
        QUARTERLY = "quarterly", "Quarterly"
        SEASON = "season", "Full Class / Season"

    studio = models.ForeignKey(
        Studio,
        on_delete=models.CASCADE,
        related_name="tuition_plans",
    )

    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)

    frequency = models.CharField(
        max_length=20,
        choices=BillingFrequency.choices,
        default=BillingFrequency.MONTHLY,
    )

    # LEGACY ONLY. Do not use for enrollment-driven billing.
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        editable=False,
    )

    registration_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    late_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    grace_period_days = models.PositiveIntegerField(default=0)
    grace_period_enabled = models.BooleanField(default=True)
    # Studio staff always decide whether to withdraw students; there is no auto-removal.
    overdue_reminders_enabled = models.BooleanField(default=False)
    overdue_notice_enabled = models.BooleanField(default=True)
    grace_warning_notice_enabled = models.BooleanField(default=True)
    resolved_notice_enabled = models.BooleanField(default=True)
    overdue_template_id = models.PositiveIntegerField(null=True, blank=True)
    grace_warning_template_id = models.PositiveIntegerField(null=True, blank=True)
    grace_expired_template_id = models.PositiveIntegerField(null=True, blank=True)
    resolved_template_id = models.PositiveIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

        constraints = [
            models.UniqueConstraint(
                fields=["studio", "name"],
                name="unique_tuition_plan_name_per_studio",
            )
        ]

    def clean(self):
        super().clean()

        if self.registration_fee < 0:
            raise ValidationError(
                {
                    "registration_fee": (
                        "Registration fee cannot be negative."
                    )
                }
            )

        if self.late_fee < 0:
            raise ValidationError(
                {"late_fee": "Late fee cannot be negative."}
            )

    def __str__(self):
        return f"{self.name} ({self.get_frequency_display()})"


class StudioTuitionSettings(models.Model):
    class PricingMode(models.TextChoices):
        PER_CLASS = "per_class", "Per-Class Tuition"
        STUDIO_WIDE = "studio_wide", "Studio-Wide Tuition"

    class StudioWideMethod(models.TextChoices):
        FLAT_HOURLY = "flat_hourly", "Flat Hourly Rate"
        TIERED_HOURLY = "tiered_hourly", "Tiered Hourly Rates"

    studio = models.OneToOneField(
        Studio, on_delete=models.CASCADE, related_name="tuition_settings"
    )
    pricing_mode = models.CharField(
        max_length=20, choices=PricingMode.choices, default=PricingMode.PER_CLASS
    )
    studio_wide_method = models.CharField(
        max_length=20,
        choices=StudioWideMethod.choices,
        default=StudioWideMethod.TIERED_HOURLY,
    )
    flat_hourly_rate = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    additional_hour_rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=(
            "Optional rate used after the final tier. If blank, Encore "
            "continues using the final tier rate."
        ),
    )
    family_monthly_cap = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    default_tuition_plan = models.ForeignKey(
        "TuitionPlan",
        on_delete=models.SET_NULL,
        related_name="studio_tuition_defaults",
        null=True,
        blank=True,
    )
    overdue_grace_days = models.PositiveSmallIntegerField(default=7, help_text="Calendar days after the charge due date before an attendance review is eligible.")
    overdue_email_enabled = models.BooleanField(default=False, help_text="Off by default: enable after reviewing email templates.")
    overdue_template_id = models.PositiveIntegerField(null=True, blank=True, help_text="Optional ID of this studio's EmailTemplate for overdue notices.")
    grace_warning_template_id = models.PositiveIntegerField(null=True, blank=True)
    grace_expired_template_id = models.PositiveIntegerField(null=True, blank=True)
    resolved_template_id = models.PositiveIntegerField(null=True, blank=True)
    attendance_review_enabled = models.BooleanField(default=False, help_text="Flag overdue accounts for staff review only; never automatically mark a student absent.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        super().clean()
        for field_name in [
            "flat_hourly_rate",
            "additional_hour_rate",
            "family_monthly_cap",
        ]:
            value = getattr(self, field_name)
            if value is not None and value < Decimal("0.00"):
                raise ValidationError({field_name: "Amount cannot be negative."})

        if (
            self.default_tuition_plan_id
            and self.default_tuition_plan.studio_id != self.studio_id
        ):
            raise ValidationError(
                {"default_tuition_plan": "Billing policy must belong to this studio."}
            )

        if self.pricing_mode == self.PricingMode.STUDIO_WIDE:
            if self.default_tuition_plan_id is None:
                raise ValidationError(
                    {
                        "default_tuition_plan": (
                            "Choose a default billing policy for studio-wide tuition."
                        )
                    }
                )
            if (
                self.studio_wide_method == self.StudioWideMethod.FLAT_HOURLY
                and self.flat_hourly_rate is None
            ):
                raise ValidationError(
                    {"flat_hourly_rate": "Enter the studio-wide hourly rate."}
                )

    @property
    def is_studio_wide(self):
        return self.pricing_mode == self.PricingMode.STUDIO_WIDE

    def __str__(self):
        return f"{self.studio.name} Tuition Settings"


class TuitionRateTier(models.Model):
    settings = models.ForeignKey(
        StudioTuitionSettings, on_delete=models.CASCADE, related_name="rate_tiers"
    )
    hour_number = models.PositiveIntegerField()
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ["hour_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["settings", "hour_number"],
                name="unique_tuition_hour_tier_per_studio",
            )
        ]

    def clean(self):
        super().clean()
        if self.hour_number < 1:
            raise ValidationError({"hour_number": "Hour number must be at least 1."})
        if self.hourly_rate < Decimal("0.00"):
            raise ValidationError({"hourly_rate": "Rate cannot be negative."})

    def __str__(self):
        return f"Hour {self.hour_number}: ${self.hourly_rate}"


class RecurringChargeSchedule(models.Model):
    class ScheduleType(models.TextChoices):
        TUITION = "tuition", "Tuition"
        REGISTRATION = "registration", "Registration Fee"
        OTHER = "other", "Other"

    account = models.ForeignKey(
        FamilyAccount,
        on_delete=models.CASCADE,
        related_name="recurring_schedules",
    )

    # Normal tuition schedules should originate from an Enrollment.
    enrollment = models.OneToOneField(
        Enrollment,
        on_delete=models.CASCADE,
        related_name="billing_schedule",
        null=True,
        blank=True,
    )

    student = models.ForeignKey(
        Student,
        on_delete=models.SET_NULL,
        related_name="billing_schedules",
        null=True,
        blank=True,
    )

    class_instance = models.ForeignKey(
        Class,
        on_delete=models.SET_NULL,
        related_name="billing_schedules",
        null=True,
        blank=True,
    )

    season = models.ForeignKey(
        Season,
        on_delete=models.SET_NULL,
        related_name="billing_schedules",
        null=True,
        blank=True,
    )

    tuition_plan = models.ForeignKey(
        TuitionPlan,
        on_delete=models.PROTECT,
        related_name="recurring_schedules",
    )

    schedule_type = models.CharField(
        max_length=20,
        choices=ScheduleType.choices,
        default=ScheduleType.TUITION,
    )

    universal_tuition = models.BooleanField(
        default=False,
        help_text="True for a family-level studio-wide tuition schedule.",
    )

    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    next_charge_date = models.DateField(null=True, blank=True)

    # Snapshot of the enrollment/class price at schedule creation.
    # Not manually entered for normal enrollment billing.
    amount_override = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )

    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["next_charge_date", "start_date"]

    @property
    def amount(self):
        if self.enrollment_id:
            if self.enrollment.tuition_override is not None:
                return self.enrollment.tuition_override

            return (
                self.enrollment.class_instance.tuition_amount
                or Decimal("0.00")
            )

        if self.amount_override is not None:
            return self.amount_override

        if self.class_instance_id:
            return self.class_instance.tuition_amount or Decimal("0.00")

        return Decimal("0.00")

    def clean(self):
        super().clean()

        studio_id = self.account.studio_id

        if self.enrollment_id:
            if self.enrollment.class_instance.studio_id != studio_id:
                raise ValidationError(
                    {
                        "enrollment": (
                            "Enrollment must belong to the same studio "
                            "as the billing account."
                        )
                    }
                )

            if (
                self.enrollment.student.family_id
                != self.account.family_id
            ):
                raise ValidationError(
                    {
                        "enrollment": (
                            "Enrollment student must belong to "
                            "the billing account family."
                        )
                    }
                )

        if (
            self.student_id
            and self.student.studio_id != studio_id
        ):
            raise ValidationError(
                {"student": "Student must belong to the same studio."}
            )

        if (
            self.class_instance_id
            and self.class_instance.studio_id != studio_id
        ):
            raise ValidationError(
                {"class_instance": "Class must belong to the same studio."}
            )

        if (
            self.season_id
            and self.season.studio_id != studio_id
        ):
            raise ValidationError(
                {"season": "Season must belong to the same studio."}
            )

        if (
            self.tuition_plan_id
            and self.tuition_plan.studio_id != studio_id
        ):
            raise ValidationError(
                {"tuition_plan": "Tuition policy must belong to the same studio."}
            )

        if self.end_date and self.end_date < self.start_date:
            raise ValidationError(
                {"end_date": "End date cannot be before start date."}
            )

    def __str__(self):
        return f"{self.account.family} - {self.tuition_plan.name}"


class Charge(models.Model):
    class ChargeType(models.TextChoices):
        TUITION = "tuition", "Tuition"
        REGISTRATION = "registration", "Registration Fee"
        LATE_FEE = "late_fee", "Late Fee"
        COSTUME = "costume", "Costume"
        PERFORMANCE = "performance", "Performance Fee"
        MERCHANDISE = "merchandise", "Merchandise"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        OPEN = "open", "Open"
        PARTIALLY_PAID = "partially_paid", "Partially Paid"
        PAID = "paid", "Paid"
        VOID = "void", "Void"

    account = models.ForeignKey(
        FamilyAccount,
        on_delete=models.CASCADE,
        related_name="charges",
    )

    enrollment = models.ForeignKey(
        Enrollment,
        on_delete=models.SET_NULL,
        related_name="billing_charges",
        null=True,
        blank=True,
    )

    student = models.ForeignKey(
        Student,
        on_delete=models.SET_NULL,
        related_name="charges",
        null=True,
        blank=True,
    )

    class_instance = models.ForeignKey(
        Class,
        on_delete=models.SET_NULL,
        related_name="charges",
        null=True,
        blank=True,
    )

    recurring_schedule = models.ForeignKey(
        RecurringChargeSchedule,
        on_delete=models.SET_NULL,
        related_name="charges",
        null=True,
        blank=True,
    )

    charge_type = models.CharField(
        max_length=30,
        choices=ChargeType.choices,
        default=ChargeType.TUITION,
    )

    description = models.CharField(max_length=255)

    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
    )

    due_date = models.DateField(null=True, blank=True)
    service_period_start = models.DateField(null=True, blank=True)
    service_period_end = models.DateField(null=True, blank=True)

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN,
    )

    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def paid_amount(self):
        return (
            self.payment_allocations
            .aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )

    @property
    def credit_amount(self):
        return (
            self.credit_allocations
            .aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )

    @property
    def balance_remaining(self):
        remaining = (
            self.amount
            - self.paid_amount
            - self.credit_amount
        )

        return max(remaining, Decimal("0.00"))

    def refresh_status_from_balance(self):
        if self.status == self.Status.VOID:
            return

        remaining = self.balance_remaining

        if remaining <= Decimal("0.00"):
            self.status = self.Status.PAID
        elif remaining < self.amount:
            self.status = self.Status.PARTIALLY_PAID
        else:
            self.status = self.Status.OPEN

        self.save(
            update_fields=[
                "status",
                "updated_at",
            ]
        )

    def clean(self):
        super().clean()

        if self.amount < 0:
            raise ValidationError(
                {"amount": "Charge amount cannot be negative."}
            )

        if (
            self.student_id
            and self.student.studio_id != self.account.studio_id
        ):
            raise ValidationError(
                {"student": "Student must belong to the same studio."}
            )

        if (
            self.student_id
            and self.student.family_id
            and self.student.family_id != self.account.family_id
        ):
            raise ValidationError(
                {"student": "Student must belong to this billing family."}
            )

        if (
            self.class_instance_id
            and self.class_instance.studio_id != self.account.studio_id
        ):
            raise ValidationError(
                {"class_instance": "Class must belong to the same studio."}
            )

    def __str__(self):
        return (
            f"{self.account.family} - "
            f"{self.description} - ${self.amount}"
        )


class Payment(models.Model):
    class Method(models.TextChoices):
        CASH = "cash", "Cash"
        CHECK = "check", "Check"
        CARD = "card", "Card"
        ACH = "ach", "ACH / Bank"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        REFUNDED = "refunded", "Refunded"
        VOID = "void", "Void"

    account = models.ForeignKey(
        FamilyAccount,
        on_delete=models.CASCADE,
        related_name="payments",
    )

    amount = models.DecimalField(max_digits=10, decimal_places=2)

    method = models.CharField(
        max_length=20,
        choices=Method.choices,
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.SUCCEEDED,
    )

    paid_at = models.DateTimeField(default=timezone.now)

    external_reference = models.CharField(
        max_length=255,
        blank=True,
    )

    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-paid_at"]

    @property
    def allocated_amount(self):
        return (
            self.allocations
            .aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )

    @property
    def unallocated_amount(self):
        refunded = (self.refunds.filter(status=PaymentRefund.Status.SUCCEEDED)
                    .aggregate(total=Sum("amount"))["total"] or Decimal("0.00"))
        return max(self.amount - refunded - self.allocated_amount, Decimal("0.00"))

    def clean(self):
        super().clean()

        if self.amount <= 0:
            raise ValidationError(
                {"amount": "Payment amount must be greater than zero."}
            )

    def __str__(self):
        return (
            f"{self.account.family} - "
            f"${self.amount} - {self.get_method_display()}"
        )


class PaymentRefund(models.Model):
    """One Stripe refund for one payment allocation; never repurpose Payment.status."""
    class Status(models.TextChoices):
        PROCESSING = "processing", "Processing"
        PENDING = "pending", "Pending at Stripe"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        CANCELED = "canceled", "Canceled"

    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name="refunds")
    charge = models.ForeignKey(Charge, on_delete=models.PROTECT, related_name="refunds")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PROCESSING)
    reason = models.CharField(max_length=30)
    notes = models.TextField()
    requested_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True)
    stripe_refund_id = models.CharField(max_length=255, blank=True, unique=True, null=True)
    stripe_account_id = models.CharField(max_length=255)
    idempotency_key = models.CharField(max_length=100, unique=True)
    last_error = models.TextField(blank=True)
    ledger_applied = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]


class PaymentAllocation(models.Model):
    payment = models.ForeignKey(
        Payment,
        on_delete=models.CASCADE,
        related_name="allocations",
    )

    charge = models.ForeignKey(
        Charge,
        on_delete=models.CASCADE,
        related_name="payment_allocations",
    )

    amount = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

        constraints = [
            models.UniqueConstraint(
                fields=["payment", "charge"],
                name="unique_payment_charge_allocation",
            )
        ]

    def clean(self):
        super().clean()

        if self.amount <= 0:
            raise ValidationError(
                {"amount": "Allocation must be greater than zero."}
            )

        if (
            self.payment_id
            and self.charge_id
            and self.payment.account_id != self.charge.account_id
        ):
            raise ValidationError(
                "Payment and charge must belong to the same family account."
            )

        existing_payment_allocated = (
            self.payment.allocations
            .exclude(pk=self.pk)
            .aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )

        if (
            existing_payment_allocated + self.amount
            > self.payment.amount
        ):
            raise ValidationError(
                {
                    "amount": (
                        "This allocation exceeds the payment's "
                        "remaining unallocated amount."
                    )
                }
            )

        existing_charge_allocated = (
            self.charge.payment_allocations
            .exclude(pk=self.pk)
            .aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )

        existing_credit_allocated = (
            self.charge.credit_allocations
            .aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )

        if (
            existing_charge_allocated
            + existing_credit_allocated
            + self.amount
            > self.charge.amount
        ):
            raise ValidationError(
                {"amount": "This allocation exceeds the charge balance."}
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        self.charge.refresh_status_from_balance()

    def delete(self, *args, **kwargs):
        charge = self.charge
        super().delete(*args, **kwargs)
        charge.refresh_status_from_balance()


class Credit(models.Model):
    class CreditType(models.TextChoices):
        MANUAL = "manual", "Manual Credit"
        DISCOUNT = "discount", "Discount"
        REFUND = "refund", "Refund Credit"
        SCHOLARSHIP = "scholarship", "Scholarship"
        PROMOTION = "promotion", "Promotion"
        OTHER = "other", "Other"

    account = models.ForeignKey(
        FamilyAccount,
        on_delete=models.CASCADE,
        related_name="credits",
    )

    student = models.ForeignKey(
        Student,
        on_delete=models.SET_NULL,
        related_name="credits",
        null=True,
        blank=True,
    )

    credit_type = models.CharField(
        max_length=20,
        choices=CreditType.choices,
        default=CreditType.MANUAL,
    )

    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    is_void = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def allocated_amount(self):
        return (
            self.allocations
            .aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )

    @property
    def remaining_amount(self):
        return max(
            self.amount - self.allocated_amount,
            Decimal("0.00"),
        )

    def clean(self):
        super().clean()

        if self.amount <= 0:
            raise ValidationError(
                {"amount": "Credit amount must be greater than zero."}
            )


class CreditAllocation(models.Model):
    credit = models.ForeignKey(
        Credit,
        on_delete=models.CASCADE,
        related_name="allocations",
    )

    charge = models.ForeignKey(
        Charge,
        on_delete=models.CASCADE,
        related_name="credit_allocations",
    )

    amount = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

        constraints = [
            models.UniqueConstraint(
                fields=["credit", "charge"],
                name="unique_credit_charge_allocation",
            )
        ]

    def clean(self):
        super().clean()

        if self.amount <= 0:
            raise ValidationError(
                {"amount": "Allocation must be greater than zero."}
            )

        if (
            self.credit_id
            and self.charge_id
            and self.credit.account_id != self.charge.account_id
        ):
            raise ValidationError(
                "Credit and charge must belong to the same family account."
            )

        existing_credit_allocated = (
            self.credit.allocations
            .exclude(pk=self.pk)
            .aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )

        if (
            existing_credit_allocated + self.amount
            > self.credit.amount
        ):
            raise ValidationError(
                {"amount": "This allocation exceeds the credit amount."}
            )

        existing_payment_allocated = (
            self.charge.payment_allocations
            .aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )

        existing_charge_credit = (
            self.charge.credit_allocations
            .exclude(pk=self.pk)
            .aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )

        if (
            existing_payment_allocated
            + existing_charge_credit
            + self.amount
            > self.charge.amount
        ):
            raise ValidationError(
                {"amount": "This allocation exceeds the charge balance."}
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        self.charge.refresh_status_from_balance()

    def delete(self, *args, **kwargs):
        charge = self.charge
        super().delete(*args, **kwargs)
        charge.refresh_status_from_balance()


class StudioSubscription(models.Model):
    class PlanTier(models.TextChoices):
        ESSENTIALS = "essentials", "Essentials"
        PRO = "pro", "Pro"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending Activation"
        ACTIVE = "active", "Active"
        PAST_DUE = "past_due", "Past Due"
        GRACE = "grace", "Grace Period"
        CANCEL_AT_PERIOD_END = (
            "cancel_at_period_end",
            "Cancels at Period End",
        )
        CANCELLED = "cancelled", "Cancelled"
        INCOMPLETE = "incomplete", "Incomplete"

    studio = models.OneToOneField(
        Studio,
        on_delete=models.CASCADE,
        related_name="subscription",
    )

    plan_tier = models.CharField(
        max_length=20,
        choices=PlanTier.choices,
    )

    student_band = models.CharField(
        max_length=30,
        default="0_100",
    )

    drawing_board_enabled = models.BooleanField(
        default=False,
    )

    current_monthly_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.PENDING,
    )

    stripe_customer_id = models.CharField(
        max_length=255,
        blank=True,
    )

    stripe_subscription_id = models.CharField(
        max_length=255,
        blank=True,
    )

    stripe_software_item_id = models.CharField(
        max_length=255,
        blank=True,
    )

    stripe_drawing_board_item_id = models.CharField(
        max_length=255,
        blank=True,
    )

    current_period_start = models.DateTimeField(
        null=True,
        blank=True,
    )

    current_period_end = models.DateTimeField(
        null=True,
        blank=True,
    )

    cancel_at_period_end = models.BooleanField(
        default=False,
    )

    grace_period_ends_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    pending_plan_tier = models.CharField(
        max_length=20,
        choices=PlanTier.choices,
        blank=True,
    )

    pending_student_band = models.CharField(
        max_length=30,
        blank=True,
    )

    pending_drawing_board_enabled = models.BooleanField(
        null=True,
        blank=True,
    )

    payments_connected = models.BooleanField(
        default=False,
    )

    stripe_test_connected_account_id = models.CharField(max_length=255, blank=True)

    stripe_connected_account_id = models.CharField(
        max_length=255,
        blank=True,
    )

    stripe_connect_details_submitted = models.BooleanField(
        default=False,
    )

    stripe_connect_charges_enabled = models.BooleanField(
        default=False,
    )

    stripe_connect_payouts_enabled = models.BooleanField(
        default=False,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    def __str__(self):
        return (
            f"{self.studio.name} - "
            f"{self.get_plan_tier_display()}"
        )


class StudioSignupIntent(models.Model):
    class Status(models.TextChoices):
        CREATED = "created", "Created"
        CHECKOUT_CREATED = "checkout_created", "Checkout Created"
        PAID = "paid", "Paid"
        CANCELLED = "cancelled", "Cancelled"
        EXPIRED = "expired", "Expired"

    owner_email = models.EmailField()

    owner_first_name = models.CharField(
        max_length=100,
    )

    owner_last_name = models.CharField(
        max_length=100,
    )

    owner_username = models.CharField(
        max_length=150,
    )

    owner_password_hash = models.CharField(
        max_length=255,
    )

    studio_name = models.CharField(
        max_length=255,
    )

    studio_email = models.EmailField(
        blank=True,
    )

    studio_phone = models.CharField(
        max_length=50,
        blank=True,
    )

    plan_tier = models.CharField(
        max_length=20,
        choices=StudioSubscription.PlanTier.choices,
    )

    drawing_board_enabled = models.BooleanField(
        default=False,
    )

    student_band = models.CharField(
        max_length=30,
        default="0_100",
    )

    monthly_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
    )

    terms_version = models.CharField(
        max_length=20,
        default="2026-10-02",
    )

    terms_accepted_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    purchase_confirmation_sent_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    welcome_email_sent_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    stripe_checkout_session_id = models.CharField(
        max_length=255,
        blank=True,
    )

    stripe_customer_id = models.CharField(
        max_length=255,
        blank=True,
    )

    stripe_subscription_id = models.CharField(
        max_length=255,
        blank=True,
    )

    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.CREATED,
    )

    studio = models.OneToOneField(
        Studio,
        on_delete=models.SET_NULL,
        related_name="signup_intent",
        null=True,
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
            "-created_at",
        ]

    def __str__(self):
        return (
            f"{self.studio_name} - "
            f"{self.owner_email}"
        )


class SubscriptionNotice(models.Model):
    class NoticeType(models.TextChoices):
        PRICE_CHANGE = "price_change", "Price Change"
        PAYMENT_FAILED = "payment_failed", "Payment Failed"
        PAYMENT_RECOVERED = "payment_recovered", "Payment Recovered"
        PLAN_CHANGE = "plan_change", "Plan Change"
        CANCELLATION = "cancellation", "Cancellation"
        GENERAL = "general", "General"

    studio = models.ForeignKey(
        Studio,
        on_delete=models.CASCADE,
        related_name="subscription_notices",
    )

    notice_type = models.CharField(
        max_length=30,
        choices=NoticeType.choices,
        default=NoticeType.GENERAL,
    )

    title = models.CharField(
        max_length=180,
    )

    message = models.TextField()

    is_read = models.BooleanField(
        default=False,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = [
            "-created_at",
        ]

    def __str__(self):
        return self.title


class FamilyAutoPayProfile(models.Model):
    """A separate Stripe customer/payment method per family and Stripe mode."""
    account = models.ForeignKey(FamilyAccount, on_delete=models.CASCADE, related_name="autopay_profiles")
    mode = models.CharField(max_length=4, choices=[("test", "Test"), ("live", "Live")])
    connected_account_id = models.CharField(max_length=255)
    stripe_customer_id = models.CharField(max_length=255, blank=True)
    stripe_payment_method_id = models.CharField(max_length=255, blank=True)
    payment_method_type = models.CharField(max_length=30, blank=True)
    card_brand = models.CharField(max_length=30, blank=True)
    card_last4 = models.CharField(max_length=4, blank=True)
    enabled_at = models.DateTimeField(null=True, blank=True)
    consent_user = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["account", "mode"], name="unique_family_autopay_mode")]

    @property
    def is_enabled(self):
        return bool(self.enabled_at and self.stripe_payment_method_id)


class FamilyAutoPayAttempt(models.Model):
    """One attempt ledger per generated tuition charge, to prevent double billing."""
    charge = models.OneToOneField(Charge, on_delete=models.PROTECT, related_name="autopay_attempt")
    profile = models.ForeignKey(FamilyAutoPayProfile, on_delete=models.PROTECT, related_name="attempts")
    stripe_payment_intent_id = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=30, default="pending")
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class BillingNoticeDelivery(models.Model):
    """Deduplicate overdue milestones per charge; preserve sending outcomes."""
    class State(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"
    charge = models.ForeignKey(Charge, on_delete=models.PROTECT, related_name="billing_notices")
    event = models.CharField(max_length=40)
    status = models.CharField(max_length=12, choices=State.choices, default=State.PENDING)
    error = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["charge", "event"], name="billing_notice_per_charge_event")]


class FamilyBillingHold(models.Model):
    """Review flag. This model alone does NOT change attendance or enrollment."""
    class Status(models.TextChoices):
        REVIEW = "review", "Needs review"
        ACTIVE = "active", "Approved review flag (not enforced)"
        RELEASED = "released", "Released"
    account = models.OneToOneField(FamilyAccount, on_delete=models.CASCADE, related_name="billing_hold")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.REVIEW)
    reason = models.TextField(blank=True)
    reviewed_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class FamilyWithdrawalRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending studio review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
    account = models.ForeignKey(FamilyAccount, on_delete=models.CASCADE, related_name="withdrawal_requests")
    enrollment = models.ForeignKey(Enrollment, on_delete=models.PROTECT, related_name="withdrawal_requests")
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    requested_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="requested_withdrawals")
    reviewed_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_withdrawals")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["-created_at"]


class FamilyBillingAction(models.Model):
    """Immutable administrator decision log. Never deletes financial history."""
    account = models.ForeignKey(FamilyAccount, on_delete=models.PROTECT, related_name="billing_actions")
    charge = models.ForeignKey(Charge, on_delete=models.PROTECT, null=True, blank=True, related_name="review_actions")
    performed_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=40)
    reason = models.TextField()
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class ImportedFamilyTuitionReview(models.Model):
    """Explicit administrator adjustment for an imported family's season cutover."""
    studio = models.ForeignKey(Studio, on_delete=models.CASCADE)
    family = models.ForeignKey(Family, on_delete=models.CASCADE)
    season = models.ForeignKey(Season, on_delete=models.CASCADE)
    amount_override = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["studio", "family", "season"], name="unique_imported_family_tuition_review")]


class BillingEmailDelivery(models.Model):
    """An event/recipient outbox; retries never create another event email."""
    account = models.ForeignKey(FamilyAccount, on_delete=models.CASCADE, related_name="email_deliveries")
    event_key = models.CharField(max_length=200)
    event_type = models.CharField(max_length=40)
    recipient = models.EmailField()
    subject = models.CharField(max_length=255)
    body = models.TextField()
    status = models.CharField(max_length=16, default="pending", choices=[
        ("pending", "Pending"), ("sending", "Sending"),
        ("sent", "Sent"), ("failed", "Failed")])
    provider_message_id = models.CharField(max_length=255, blank=True)
    error = models.TextField(blank=True)
    attempts = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["account", "event_key", "recipient"], name="unique_billing_email_delivery")]
        ordering = ["-created_at"]
