from django import forms

from families.models import Family

from .models import Student


class EncoreStudentForm(forms.ModelForm):
    class Meta:
        model = Student

        exclude = [
            "studio",
            "user",
            "created_at",
            "updated_at",
        ]

        widgets = {
            "birthday": forms.DateInput(
                attrs={"type": "date"}
            ),
            "medical_conditions": forms.Textarea(
                attrs={"rows": 3}
            ),
            "allergies": forms.Textarea(
                attrs={"rows": 3}
            ),
            "comments": forms.Textarea(
                attrs={"rows": 3}
            ),
        }

    def __init__(self, *args, studio=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.studio = studio

        if studio is not None and "family" in self.fields:
            self.fields["family"].queryset = Family.objects.filter(
                studio=studio,
                is_active=True,
            ).order_by("family_name", "id")

        for name, field in self.fields.items():
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
