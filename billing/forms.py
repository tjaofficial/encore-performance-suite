from decimal import Decimal
from django.db.models import Q
from django.utils import timezone
from .models import PaymentAllocation
from .refund_services import eligible_allocations, available_for_refund
from django import forms
from django.forms import inlineformset_factory

from classes.models import Class
from students.models import Student

from .models import (
    Charge,
    Credit,
    Payment,
    StudioTuitionSettings,
    TuitionPlan,
    TuitionRateTier,
)


class ChargeForm(forms.ModelForm):
    class Meta:
        model = Charge
        fields = [
            "student",
            "class_instance",
            "charge_type",
            "description",
            "amount",
            "due_date",
            "service_period_start",
            "service_period_end",
            "status",
            "notes",
        ]

        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "service_period_start": forms.DateInput(
                attrs={"type": "date"}
            ),
            "service_period_end": forms.DateInput(
                attrs={"type": "date"}
            ),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, account=None, **kwargs):
        super().__init__(*args, **kwargs)

        if account is not None:
            self.fields["student"].queryset = Student.objects.filter(
                family=account.family,
                studio=account.studio,
                is_active=True,
            ).order_by("last_name", "first_name")

            self.fields["class_instance"].queryset = Class.objects.filter(
                studio=account.studio,
                is_active=True,
            ).order_by("name")

        for field in self.fields.values():
            field.widget.attrs["class"] = "encore-input"


class PaymentForm(forms.ModelForm):
    auto_allocate = forms.BooleanField(
        required=False,
        initial=True,
        label="Automatically apply to oldest open charges",
    )

    class Meta:
        model = Payment
        fields = [
            "amount",
            "method",
            "status",
            "paid_at",
            "external_reference",
            "notes",
        ]

        widgets = {
            "paid_at": forms.DateTimeInput(
                attrs={"type": "datetime-local"}
            ),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "encore-checkbox"
            else:
                field.widget.attrs["class"] = "encore-input"


class CreditForm(forms.ModelForm):
    auto_allocate = forms.BooleanField(
        required=False,
        initial=True,
        label="Automatically apply to oldest open charges",
    )

    class Meta:
        model = Credit
        fields = [
            "student",
            "credit_type",
            "description",
            "amount",
            "notes",
        ]

        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, account=None, **kwargs):
        super().__init__(*args, **kwargs)

        if account is not None:
            self.fields["student"].queryset = Student.objects.filter(
                family=account.family,
                studio=account.studio,
                is_active=True,
            ).order_by("last_name", "first_name")

        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "encore-checkbox"
            else:
                field.widget.attrs["class"] = "encore-input"


class TuitionPlanForm(forms.ModelForm):
    class Meta:
        model = TuitionPlan
        fields = [
            "name",
            "description",
            "frequency",
            "registration_fee",
            "late_fee",
            "grace_period_enabled",
            "grace_period_days",
            "overdue_notice_enabled",
            "grace_warning_notice_enabled",
            "resolved_notice_enabled",
            "overdue_template_id",
            "grace_warning_template_id",
            "grace_expired_template_id",
            "resolved_template_id",
            "is_active",
        ]

        labels = {
            "frequency": "Billing Frequency",
        }

        help_texts = {
            "frequency": (
                "Controls how a Class tuition amount is billed. "
                "The price itself lives on the Class."
            ),
        }

        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        from communications.models import EmailTemplate
        studio = getattr(self.instance, "studio", None)
        options = [("", "Use Encore default message")]
        if studio is not None and studio.pk:
            options.extend(
                (str(t.pk), t.name)
                for t in EmailTemplate.objects.filter(studio=studio, is_active=True).order_by("name")
            )
        for name in ("overdue_template_id", "grace_warning_template_id", "grace_expired_template_id", "resolved_template_id"):
            self.fields[name].widget = forms.Select(choices=options)
        self.fields["grace_period_enabled"].label = "Enable a grace period before overdue review"
        self.fields["grace_period_days"].widget.attrs.update({"min": "0", "max": "90"})
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "encore-checkbox"
            else:
                field.widget.attrs["class"] = "encore-input"

    def clean_grace_period_days(self):
        value = self.cleaned_data["grace_period_days"]
        if value > 90:
            raise forms.ValidationError("Grace period cannot exceed 90 days.")
        return value

    def clean(self):
        cleaned = super().clean()
        from communications.models import EmailTemplate
        studio = getattr(self.instance, "studio", None)
        if studio and studio.pk:
            for name in ("overdue_template_id", "grace_warning_template_id", "grace_expired_template_id", "resolved_template_id"):
                template_id = cleaned.get(name)
                if template_id and not EmailTemplate.objects.filter(studio=studio, pk=template_id, is_active=True).exists():
                    self.add_error(name, "Select an active template from this studio.")
        return cleaned


class SubscriptionPlanChangeForm(forms.Form):
    plan_tier = forms.ChoiceField(
        choices=[
            ("essentials", "Essentials"),
            ("pro", "Pro"),
        ],
    )

    def __init__(
        self,
        *args,
        current_plan=None,
        **kwargs,
    ):
        super().__init__(
            *args,
            **kwargs,
        )

        if current_plan:
            self.fields[
                "plan_tier"
            ].initial = current_plan

        self.fields[
            "plan_tier"
        ].widget.attrs[
            "class"
        ] = "encore-input"


class DrawingBoardChangeForm(forms.Form):
    enabled = forms.BooleanField(
        required=False,
        label="Enable Drawing Board",
    )


class CancelSubscriptionForm(forms.Form):
    confirm = forms.BooleanField(
        required=True,
        label=(
            "I understand Encore will remain available "
            "through the end of the current billing period."
        ),
    )


class StudioTuitionSettingsForm(forms.ModelForm):
    class Meta:
        model = StudioTuitionSettings
        fields = [
            "pricing_mode",
            "studio_wide_method",
            "flat_hourly_rate",
            "additional_hour_rate",
            "family_monthly_cap",
            "default_tuition_plan",
        ]
        widgets = {
            "pricing_mode": forms.RadioSelect,
            "studio_wide_method": forms.RadioSelect,
            "flat_hourly_rate": forms.NumberInput(attrs={"min": 0, "step": "0.01"}),
            "additional_hour_rate": forms.NumberInput(attrs={"min": 0, "step": "0.01"}),
            "family_monthly_cap": forms.NumberInput(attrs={"min": 0, "step": "0.01"}),
        }

    def __init__(self, *args, studio=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.studio = studio
        if studio is not None:
            self.fields["default_tuition_plan"].queryset = TuitionPlan.objects.filter(
                studio=studio, is_active=True
            ).order_by("name")
        for field in self.fields.values():
            if isinstance(field.widget, (forms.RadioSelect, forms.CheckboxInput)):
                continue
            field.widget.attrs["class"] = "encore-input"

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("pricing_mode") == StudioTuitionSettings.PricingMode.STUDIO_WIDE:
            if not cleaned.get("default_tuition_plan"):
                self.add_error(
                    "default_tuition_plan",
                    "Choose the billing policy Encore should use for studio-wide tuition.",
                )
            if (
                cleaned.get("studio_wide_method")
                == StudioTuitionSettings.StudioWideMethod.FLAT_HOURLY
                and cleaned.get("flat_hourly_rate") is None
            ):
                self.add_error("flat_hourly_rate", "Enter the hourly rate.")
        return cleaned


class TuitionRateTierForm(forms.ModelForm):
    class Meta:
        model = TuitionRateTier
        fields = ["hour_number", "hourly_rate"]
        widgets = {
            "hour_number": forms.NumberInput(attrs={"min": 1, "step": 1}),
            "hourly_rate": forms.NumberInput(attrs={"min": 0, "step": "0.01"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "encore-input"


BaseTuitionRateTierFormSet = inlineformset_factory(
    StudioTuitionSettings,
    TuitionRateTier,
    form=TuitionRateTierForm,
    fields=["hour_number", "hourly_rate"],
    extra=1,
    can_delete=True,
)


class AdministratorRefundForm(forms.Form):
    allocation = forms.ModelChoiceField(queryset=PaymentAllocation.objects.none(), label="Current-month tuition payment")
    amount = forms.DecimalField(min_value=Decimal("0.01"), max_digits=10, decimal_places=2)
    reason = forms.ChoiceField(choices=[("class_cancelled", "Class cancellation"),
        ("withdrawal", "Student withdrawal"), ("overpayment", "Overpayment"),
        ("customer_request", "Family request"), ("exception", "Special exception")])
    notes = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), min_length=5,
        help_text="Required administrator explanation. Visible in refund audit history.")

    def __init__(self, *args, account, **kwargs):
        super().__init__(*args, **kwargs)
        today = timezone.localdate()
        self.fields["allocation"].queryset = eligible_allocations(account).filter(
            Q(charge__service_period_start__year=today.year, charge__service_period_start__month=today.month) |
            Q(charge__service_period_start__isnull=True, charge__due_date__year=today.year, charge__due_date__month=today.month))
        self.fields["allocation"].label_from_instance = lambda obj: (
            f"{obj.charge.description} | {obj.charge.student or 'Family'} | "
            f"{obj.payment.paid_at:%b %d, %Y} | ${available_for_refund(obj.payment, obj.charge):.2f} available")
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "encore-input")

    def clean(self):
        data = super().clean()
        allocation = data.get("allocation")
        amount = data.get("amount")
        if allocation and amount is not None and amount > available_for_refund(allocation.payment, allocation.charge):
            self.add_error("amount", "Refund exceeds this charge's remaining refundable payment allocation.")
        return data
