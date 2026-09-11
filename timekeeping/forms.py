from django import forms
from django.utils import timezone

from .models import ExtraWorkEntry


class ExtraWorkEntryForm(forms.ModelForm):
    hours = forms.IntegerField(
        min_value=0,
        max_value=24,
        initial=1,
        label="Hours",
    )

    minutes = forms.IntegerField(
        min_value=0,
        max_value=59,
        initial=0,
        label="Minutes",
    )

    class Meta:
        model = ExtraWorkEntry
        fields = [
            "work_date",
            "category",
            "description",
        ]

        widgets = {
            "work_date": forms.DateInput(
                attrs={
                    "type": "date",
                }
            ),
            "description": forms.TextInput(
                attrs={
                    "placeholder": (
                        "What did you work on?"
                    ),
                }
            ),
        }

    def __init__(
        self,
        *args,
        studio=None,
        user=None,
        **kwargs,
    ):
        super().__init__(
            *args,
            **kwargs,
        )

        self.studio = studio
        self.user = user

        if studio is not None:
            self.instance.studio = studio

        if user is not None:
            self.instance.user = user

        if not self.is_bound:
            self.fields["work_date"].initial = (
                self.instance.work_date
                or timezone.localdate()
            )

            if (
                self.instance.pk
                and self.instance.duration_minutes
            ):
                hours, minutes = divmod(
                    self.instance.duration_minutes,
                    60,
                )

                self.fields["hours"].initial = hours
                self.fields["minutes"].initial = minutes

        for field in self.fields.values():
            field.widget.attrs["class"] = (
                "encore-input"
            )

    def clean(self):
        cleaned = super().clean()

        hours = cleaned.get("hours") or 0
        minutes = cleaned.get("minutes") or 0

        duration_minutes = (
            hours * 60
            + minutes
        )

        if duration_minutes <= 0:
            raise forms.ValidationError(
                "Enter at least one minute of extra work."
            )

        cleaned["duration_minutes"] = (
            duration_minutes
        )

        return cleaned

    def save(self, commit=True):
        entry = super().save(
            commit=False
        )

        entry.studio = self.studio
        entry.user = self.user
        entry.duration_minutes = (
            self.cleaned_data[
                "duration_minutes"
            ]
        )

        if commit:
            entry.full_clean()
            entry.save()

        return entry
