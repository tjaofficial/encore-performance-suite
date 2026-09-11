from django import forms
from django.db.models import Q

from classes.models import Class

from .models import ClassResource


class ClassResourceForm(forms.ModelForm):
    class Meta:
        model = ClassResource
        fields = [
            "class_instance",
            "resource_type",
            "title",
            "artist",
            "description",
            "file",
            "external_url",
            "visibility",
            "sort_order",
            "is_active",
        ]

        widgets = {
            "description": forms.Textarea(
                attrs={"rows": 3}
            ),
        }

    def __init__(
        self,
        *args,
        studio=None,
        instructor=None,
        teacher_mode=False,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        if studio is not None:
            self.instance.studio = studio
            
            classes = Class.objects.filter(
                studio=studio,
                is_active=True,
            )

            if teacher_mode and instructor is not None:
                classes = classes.filter(
                    Q(instructor=instructor)
                    | Q(assistant_instructor=instructor)
                ).distinct()

            self.fields["class_instance"].queryset = (
                classes
                .select_related("season")
                .order_by("name")
            )

        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "encore-checkbox"
            else:
                current = field.widget.attrs.get("class", "")
                field.widget.attrs["class"] = (
                    f"{current} encore-input".strip()
                )
