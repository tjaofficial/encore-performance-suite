from django import forms
from django.forms import inlineformset_factory

from .models import Instructor, InstructorAvailability


class EncoreInstructorForm(forms.ModelForm):
    class Meta:
        model = Instructor
        exclude = [
            "studio",
            "user",
            "created_at",
            "updated_at",
        ]

        widgets = {
            "bio": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field in self.fields.values():
            widget = field.widget

            if isinstance(widget, forms.CheckboxInput):
                widget.attrs["class"] = "encore-checkbox"
            else:
                existing = widget.attrs.get("class", "")
                widget.attrs["class"] = (
                    f"{existing} encore-input".strip()
                )


class InstructorAvailabilityForm(forms.ModelForm):
    class Meta:
        model = InstructorAvailability
        exclude = [
            "instructor",
        ]

        widgets = {
            "start_time": forms.TimeInput(
                attrs={"type": "time"}
            ),
            "end_time": forms.TimeInput(
                attrs={"type": "time"}
            ),
            "notes": forms.Textarea(
                attrs={"rows": 2}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field in self.fields.values():
            widget = field.widget

            if isinstance(widget, forms.CheckboxInput):
                widget.attrs["class"] = "encore-checkbox"
            else:
                existing = widget.attrs.get("class", "")
                widget.attrs["class"] = (
                    f"{existing} encore-input".strip()
                )


InstructorAvailabilityFormSet = inlineformset_factory(
    Instructor,
    InstructorAvailability,
    form=InstructorAvailabilityForm,
    extra=1,
    can_delete=True,
)
