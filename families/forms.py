from django import forms
from django.forms import inlineformset_factory

from .models import Family, Guardian


class EncoreFamilyForm(forms.ModelForm):
    class Meta:
        model = Family

        exclude = [
            "studio",
            "created_at",
            "updated_at",
        ]

        widgets = {
            "notes": forms.Textarea(
                attrs={"rows": 3}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field in self.fields.values():
            widget = field.widget

            if isinstance(
                widget,
                (
                    forms.CheckboxInput,
                    forms.RadioSelect,
                    forms.CheckboxSelectMultiple,
                ),
            ):
                widget.attrs["class"] = "encore-checkbox"
            else:
                existing = widget.attrs.get("class", "")
                widget.attrs["class"] = (
                    f"{existing} encore-input".strip()
                )


class EncoreGuardianForm(forms.ModelForm):
    class Meta:
        model = Guardian

        exclude = [
            "family",
            "user",
            "created_at",
            "updated_at",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field in self.fields.values():
            widget = field.widget

            if isinstance(
                widget,
                (
                    forms.CheckboxInput,
                    forms.RadioSelect,
                    forms.CheckboxSelectMultiple,
                ),
            ):
                widget.attrs["class"] = "encore-checkbox"
            else:
                existing = widget.attrs.get("class", "")
                widget.attrs["class"] = (
                    f"{existing} encore-input".strip()
                )


GuardianFormSet = inlineformset_factory(
    Family,
    Guardian,
    form=EncoreGuardianForm,
    extra=1,
    can_delete=True,
)
