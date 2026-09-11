from django import forms

from classes.models import Class
from students.models import Student

from .models import Enrollment


class EncoreEnrollmentForm(forms.ModelForm):
    class Meta:
        model = Enrollment

        exclude = [
            "enrolled_at",
            "dropped_at",
            "waitlisted_at",
            "created_at",
            "updated_at",
        ]

        widgets = {
            "notes": forms.Textarea(
                attrs={"rows": 3}
            ),
        }

    def __init__(self, *args, studio=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.studio = studio

        if studio is not None:
            self.fields["student"].queryset = Student.objects.filter(
                studio=studio,
                is_active=True,
            ).order_by(
                "last_name",
                "first_name",
            )

            self.fields["class_instance"].queryset = Class.objects.filter(
                studio=studio,
                is_active=True,
            ).select_related(
                "season",
            ).order_by(
                "name",
            )

        for field in self.fields.values():
            widget = field.widget

            if isinstance(widget, forms.CheckboxInput):
                widget.attrs["class"] = "encore-checkbox"
            else:
                existing = widget.attrs.get("class", "")
                widget.attrs["class"] = (
                    f"{existing} encore-input".strip()
                )
