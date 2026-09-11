from django import forms

from classes.models import Class
from students.models import Student

from .models import Charge, Credit, Payment, TuitionPlan


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
            "grace_period_days",
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

        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "encore-checkbox"
            else:
                field.widget.attrs["class"] = "encore-input"


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
