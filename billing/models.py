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
        return (
            self.payments
            .filter(status=Payment.Status.SUCCEEDED)
            .aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )

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
        return max(
            self.amount - self.allocated_amount,
            Decimal("0.00"),
        )

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

    class PaymentMode(models.TextChoices):
        SOFTWARE_ONLY = "software_only", "Software Only"
        SOFTWARE_PAYMENTS = "software_payments", "Software + Payments"

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

    payment_mode = models.CharField(
        max_length=30,
        choices=PaymentMode.choices,
        default=PaymentMode.SOFTWARE_ONLY,
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

    pending_payment_mode = models.CharField(
        max_length=30,
        choices=PaymentMode.choices,
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

    payment_mode = models.CharField(
        max_length=30,
        choices=StudioSubscription.PaymentMode.choices,
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
