from django import forms
from django.db.models import Q

from classes.models import Class

from .models import (
    ChoreographyPlan,
    Formation,
    LightingCue,
    PerformancePrepItem,
)


class ChoreographyPlanForm(forms.ModelForm):
    class Meta:
        model = ChoreographyPlan
        fields = [
            "class_instance",
            "title",
            "song_title",
            "artist",
            "music_resource",
            "choreography_notes",
            "teacher_notes",
            "performance_notes",
        ]

        widgets = {
            "choreography_notes": forms.Textarea(
                attrs={"rows": 7}
            ),
            "teacher_notes": forms.Textarea(
                attrs={"rows": 5}
            ),
            "performance_notes": forms.Textarea(
                attrs={"rows": 5}
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
                    | Q(
                        assistant_instructor=instructor
                    )
                ).distinct()

            self.fields["class_instance"].queryset = (
                classes
                .select_related("season")
                .order_by("name")
            )

        if "music_resource" in self.fields:
            from resources.models import ClassResource

            music = ClassResource.objects.none()

            if studio is not None:
                music = ClassResource.objects.filter(
                    studio=studio,
                    resource_type=ClassResource.ResourceType.MUSIC,
                    is_active=True,
                    approval_status=ClassResource.ApprovalStatus.APPROVED,
                )

                class_id = (
                    self.instance.class_instance_id
                    if self.instance.pk
                    else None
                )

                if class_id:
                    music = music.filter(
                        class_instance_id=class_id,
                    )

            self.fields["music_resource"].queryset = (
                music.order_by(
                    "title",
                    "-created_at",
                )
            )

            self.fields["music_resource"].required = False

        for field in self.fields.values():
            field.widget.attrs["class"] = "encore-input"


class FormationForm(forms.ModelForm):
    class Meta:
        model = Formation
        fields = [
            "name",
            "section_label",
            "time_seconds",
            "sequence_order",
            "notes",
        ]

        widgets = {
            "notes": forms.Textarea(
                attrs={"rows": 3}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field in self.fields.values():
            field.widget.attrs["class"] = "encore-input"


class LightingCueForm(forms.ModelForm):
    class Meta:
        model = LightingCue
        fields = [
            "cue_number",
            "name",
            "timing",
            "color_notes",
            "action",
            "notes",
        ]

        widgets = {
            "action": forms.Textarea(
                attrs={"rows": 3}
            ),
            "notes": forms.Textarea(
                attrs={"rows": 3}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field in self.fields.values():
            field.widget.attrs["class"] = "encore-input"


class PerformancePrepItemForm(forms.ModelForm):
    class Meta:
        model = PerformancePrepItem
        fields = [
            "category",
            "title",
            "notes",
            "due_date",
            "sort_order",
            "is_complete",
        ]

        widgets = {
            "notes": forms.Textarea(
                attrs={"rows": 3}
            ),
            "due_date": forms.DateInput(
                attrs={"type": "date"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

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
