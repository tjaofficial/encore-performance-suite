from django import forms
from django.forms import inlineformset_factory

from performance.models import ChoreographyPlan

from .models import (
    Costume,
    CostumeLink,
    StudentCostumeAssignment,
)


class CostumeForm(forms.ModelForm):
    create_student_task = forms.BooleanField(
        required=False,
        label="Create a Task for Students / Guardians",
    )

    task_due_date = forms.DateField(
        required=False,
        label="Task Due Date",
        widget=forms.DateInput(
            attrs={
                "type": "date",
            }
        ),
    )

    send_notification = forms.BooleanField(
        required=False,
        label="Send a Notification",
    )

    class Meta:
        model = Costume
        fields = [
            "dance",
            "name",
            "student_notes",
            "internal_notes",
        ]

        labels = {
            "dance": "Dance",
            "name": "Costume Name",
            "student_notes": "Student / Guardian Notes",
            "internal_notes": "Internal Staff Notes",
        }

        widgets = {
            "student_notes": forms.Textarea(
                attrs={
                    "rows": 5,
                    "placeholder": (
                        "Instructions students and guardians should see."
                    ),
                }
            ),
            "internal_notes": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": (
                        "Private notes for teachers and administrators."
                    ),
                }
            ),
        }

    def __init__(
        self,
        *args,
        studio=None,
        class_instance=None,
        **kwargs,
    ):
        super().__init__(
            *args,
            **kwargs,
        )

        dances = ChoreographyPlan.objects.none()

        if studio is not None:
            dances = (
                ChoreographyPlan.objects
                .filter(
                    studio=studio,
                )
                .select_related(
                    "class_instance",
                )
            )

        if class_instance is not None:
            dances = dances.filter(
                class_instance=class_instance,
            )

        self.fields[
            "dance"
        ].queryset = dances.order_by(
            "class_instance__name",
            "title",
        )

        self.fields[
            "dance"
        ].label_from_instance = (
            lambda dance: (
                f"{dance.title or 'Untitled Dance'} "
                f"— {dance.class_instance.name}"
            )
        )

        for field in self.fields.values():
            if isinstance(
                field.widget,
                forms.CheckboxInput,
            ):
                field.widget.attrs[
                    "class"
                ] = "encore-checkbox"
            else:
                field.widget.attrs[
                    "class"
                ] = "encore-input"


class CostumeLinkForm(forms.ModelForm):
    class Meta:
        model = CostumeLink
        fields = [
            "label",
            "url",
            "notes",
        ]

        labels = {
            "label": "Link Label",
            "url": "URL",
            "notes": "Link Notes",
        }

    def __init__(
        self,
        *args,
        **kwargs,
    ):
        super().__init__(
            *args,
            **kwargs,
        )

        for field in self.fields.values():
            field.widget.attrs[
                "class"
            ] = "encore-input"


CostumeLinkFormSet = inlineformset_factory(
    Costume,
    CostumeLink,
    form=CostumeLinkForm,
    extra=1,
    can_delete=True,
)


class StudentCostumeAssignmentForm(forms.ModelForm):
    class Meta:
        model = StudentCostumeAssignment
        fields = [
            "costume_size",
            "shoe_size",
            "status",
            "student_notes",
            "internal_notes",
        ]

        widgets = {
            "student_notes": forms.Textarea(
                attrs={
                    "rows": 2,
                }
            ),
            "internal_notes": forms.Textarea(
                attrs={
                    "rows": 2,
                }
            ),
        }

    def __init__(
        self,
        *args,
        **kwargs,
    ):
        super().__init__(
            *args,
            **kwargs,
        )

        for field in self.fields.values():
            field.widget.attrs[
                "class"
            ] = "encore-input"
