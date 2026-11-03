from django import forms
from django.db.models import Q

from .models import (
    InstructorCompensation,
    PayrollSettings,
)


class PayrollUnlockForm(forms.Form):
    password = forms.CharField(
        label="Current Password",
        widget=forms.PasswordInput(
            attrs={
                "class": "encore-input",
                "autocomplete": "current-password",
                "placeholder": "Enter your Encore password",
            }
        ),
    )


class PayrollSettingsForm(forms.ModelForm):
    class Meta:
        model = PayrollSettings
        fields = [
            "pay_period_frequency",
            "pay_period_anchor_date",
            "minimum_session_minutes",
            "rounding_minutes",
            "extra_work_uses_regular_rate",
        ]
        widgets = {
            "pay_period_frequency": forms.Select(
                attrs={"class": "encore-input"}
            ),
            "pay_period_anchor_date": forms.DateInput(
                attrs={
                    "class": "encore-input",
                    "type": "date",
                }
            ),
            "minimum_session_minutes": forms.NumberInput(
                attrs={
                    "class": "encore-input",
                    "min": 1,
                    "step": 1,
                }
            ),
            "rounding_minutes": forms.Select(
                attrs={"class": "encore-input"}
            ),
            "extra_work_uses_regular_rate": forms.CheckboxInput(
                attrs={"class": "encore-checkbox"}
            ),
        }
        labels = {
            "pay_period_frequency": "Payroll Breakdown",
            "pay_period_anchor_date": "Known Pay Period Start Date",
            "minimum_session_minutes": "Minimum Paid Class Session",
            "rounding_minutes": "Additional Time Rounding",
            "extra_work_uses_regular_rate": (
                "Use Regular Hourly Rate for Extra Work"
            ),
        }
        help_texts = {
            "pay_period_frequency": (
                "Controls the default pay-period breakdown teachers will see."
            ),
            "pay_period_anchor_date": (
                "For weekly or biweekly payroll, enter any date you know was "
                "the first day of a real pay period. Encore uses that date only "
                "to keep every 7- or 14-day period aligned correctly."
            ),
            "minimum_session_minutes": (
                "A class occurrence shorter than this still pays this many minutes."
            ),
            "rounding_minutes": (
                "Applied only after the minimum paid session has been reached."
            ),
        }


class InstructorCompensationForm(forms.ModelForm):
    class Meta:
        model = InstructorCompensation
        fields = [
            "compensation_type",
            "hourly_rate",
            "salary_amount",
            "salary_basis",
            "extra_work_hourly_rate",
            "effective_start",
            "effective_end",
            "notes",
        ]
        widgets = {
            "compensation_type": forms.Select(
                attrs={"class": "encore-input"}
            ),
            "hourly_rate": forms.NumberInput(
                attrs={
                    "class": "encore-input",
                    "min": "0.01",
                    "step": "0.01",
                    "placeholder": "0.00",
                }
            ),
            "salary_amount": forms.NumberInput(
                attrs={
                    "class": "encore-input",
                    "min": "0.01",
                    "step": "0.01",
                    "placeholder": "0.00",
                }
            ),
            "salary_basis": forms.Select(
                attrs={"class": "encore-input"}
            ),
            "extra_work_hourly_rate": forms.NumberInput(
                attrs={
                    "class": "encore-input",
                    "min": "0.01",
                    "step": "0.01",
                    "placeholder": "Optional",
                }
            ),
            "effective_start": forms.DateInput(
                attrs={
                    "class": "encore-input",
                    "type": "date",
                }
            ),
            "effective_end": forms.DateInput(
                attrs={
                    "class": "encore-input",
                    "type": "date",
                }
            ),
            "notes": forms.Textarea(
                attrs={
                    "class": "encore-input",
                    "rows": 3,
                    "placeholder": "Optional internal notes",
                }
            ),
        }

    def __init__(
        self,
        *args,
        instructor,
        **kwargs,
    ):
        self.instructor = instructor
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()

        start = cleaned.get("effective_start")
        end = cleaned.get("effective_end")

        if not start:
            return cleaned

        overlaps = (
            InstructorCompensation.objects
            .filter(
                instructor=self.instructor,
            )
            .exclude(pk=self.instance.pk)
        )

        if end:
            overlaps = overlaps.filter(
                effective_start__lte=end,
            )
        overlaps = overlaps.filter(
            Q(effective_end__isnull=True)
            | Q(effective_end__gte=start)
        )

        if overlaps.exists():
            raise forms.ValidationError(
                "This date range overlaps another compensation record. "
                "End the earlier record first, or adjust these dates."
            )

        return cleaned
