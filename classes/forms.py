from django import forms
from django.forms import inlineformset_factory

from billing.models import TuitionPlan
from instructors.models import Instructor
from studios.models import StudioLocation, StudioRoom

from .models import Class, ClassMeeting, ClassType, Season


class EncoreClassForm(forms.ModelForm):
    class Meta:
        model = Class
        fields = [
            "season",
            "class_type",
            "class_id",
            "name",
            "description",
            "dress_code",
            "instructor",
            "assistant_instructor",
            "default_location",
            "capacity",
            "min_age",
            "max_age",
            "gender_restriction",
            "prerequisites",
            "allow_drop_ins",
            "drop_in_price",
            "tuition_amount",
            "tuition_plan",
            "is_active",
            "registration_open",
            "notes",
        ]

        labels = {
            "dress_code": "Dress Code",
            "tuition_amount": "Class Tuition",
            "tuition_plan": "Tuition Billing Policy",
        }

        help_texts = {
            "dress_code": (
                "Optional. Add class-specific attire, shoes, hair, "
                "or appearance requirements."
            ),
            "tuition_amount": (
                "The authoritative tuition price for this class. "
                "Enrollment billing pulls from this amount."
            ),
            "tuition_plan": (
                "Controls whether tuition is monthly, full-season, etc. "
                "The policy does not override the class price."
            ),
        }

        widgets = {
            "class_id": forms.TextInput(
                attrs={
                    "placeholder": "Example: JAZ-101",
                    "autocomplete": "off",
                }
            ),
            "name": forms.TextInput(
                attrs={
                    "placeholder": "Example: Intermediate 1 - Jazz",
                    "autocomplete": "off",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "Optional class description.",
                }
            ),
            "dress_code": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": (
                        "Example: Black leotard, pink tights, "
                        "pink ballet shoes, hair secured in a bun."
                    ),
                }
            ),
            "capacity": forms.NumberInput(
                attrs={
                    "min": 1,
                    "step": 1,
                }
            ),
            "min_age": forms.NumberInput(
                attrs={
                    "min": 0,
                    "step": 1,
                }
            ),
            "max_age": forms.NumberInput(
                attrs={
                    "min": 0,
                    "step": 1,
                }
            ),
            "drop_in_price": forms.NumberInput(
                attrs={
                    "min": 0,
                    "step": "0.01",
                    "placeholder": "0.00",
                }
            ),
            "tuition_amount": forms.NumberInput(
                attrs={
                    "min": 0,
                    "step": "0.01",
                    "placeholder": "0.00",
                }
            ),
            "notes": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Internal staff notes.",
                }
            ),
            "prerequisites": forms.SelectMultiple(
                attrs={"size": 6}
            ),
        }

    def __init__(self, *args, studio=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.studio = studio

        if studio is None:
            return

        self.fields["season"].queryset = Season.objects.filter(
            studio=studio,
        ).order_by("-start_date", "name")

        self.fields["class_type"].queryset = ClassType.objects.filter(
            studio=studio,
            is_active=True,
        ).order_by("name")

        self.fields["instructor"].queryset = Instructor.objects.filter(
            studio=studio,
            is_active=True,
        ).order_by("last_name", "first_name")

        self.fields["assistant_instructor"].queryset = Instructor.objects.filter(
            studio=studio,
            is_active=True,
        ).order_by("last_name", "first_name")

        self.fields["default_location"].queryset = StudioLocation.objects.filter(
            studio=studio,
            is_active=True,
        ).order_by("-is_primary", "name")

        self.fields["tuition_plan"].queryset = TuitionPlan.objects.filter(
            studio=studio,
            is_active=True,
        ).order_by("name")

        prerequisite_qs = Class.objects.filter(
            studio=studio,
        ).order_by("name")

        if self.instance and self.instance.pk:
            prerequisite_qs = prerequisite_qs.exclude(
                pk=self.instance.pk
            )

        self.fields["prerequisites"].queryset = prerequisite_qs

        for field in self.fields.values():
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = (
                f"{existing} encore-input".strip()
            )

        for boolean_name in [
            "allow_drop_ins",
            "is_active",
            "registration_open",
        ]:
            self.fields[boolean_name].widget.attrs["class"] = (
                "encore-checkbox"
            )


class ClassMeetingForm(forms.ModelForm):
    class Meta:
        model = ClassMeeting
        fields = [
            "day_of_week",
            "start_time",
            "duration_minutes",
            "room",
            "is_active",
            "notes",
        ]

        widgets = {
            "start_time": forms.TimeInput(
                attrs={"type": "time"}
            ),
            "duration_minutes": forms.NumberInput(
                attrs={
                    "min": 1,
                    "step": 5,
                }
            ),
            "notes": forms.TextInput(
                attrs={
                    "placeholder": "Optional meeting note",
                }
            ),
        }

    def __init__(self, *args, studio=None, **kwargs):
        super().__init__(*args, **kwargs)

        if studio is not None:
            self.fields["room"].queryset = (
                StudioRoom.objects
                .filter(
                    studio=studio,
                    is_active=True,
                )
                .select_related(
                    "location",
                )
                .order_by(
                    "location__name",
                    "name",
                )
            )

            self.fields["room"].required = False
            self.fields["room"].empty_label = "Select a room"

            class StudioRoomChoiceField(
                forms.ModelChoiceField
            ):
                def label_from_instance(
                    self,
                    room,
                ):
                    if room.location:
                        return (
                            f"{room.location.name} — "
                            f"{room.name}"
                        )

                    return room.name

            current_field = self.fields["room"]

            self.fields["room"] = StudioRoomChoiceField(
                queryset=current_field.queryset,
                required=False,
                empty_label="Select a room",
                widget=current_field.widget,
                label="Room",
            )

        for field in self.fields.values():
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = (
                f"{existing} encore-input".strip()
            )

        self.fields["is_active"].widget.attrs["class"] = (
            "encore-checkbox"
        )

    def save(
        self,
        commit=True,
    ):
        meeting = super().save(
            commit=False
        )

        if meeting.room_id:
            meeting.location = (
                meeting.room.location
            )
        else:
            meeting.location = None

        if commit:
            meeting.save()
            self.save_m2m()

        return meeting


BaseClassMeetingFormSet = inlineformset_factory(
    Class,
    ClassMeeting,
    form=ClassMeetingForm,
    fields=[
        "day_of_week",
        "start_time",
        "duration_minutes",
        "room",
        "is_active",
        "notes",
    ],
    extra=1,
    can_delete=True,
)


class StudioClassMeetingFormSet(BaseClassMeetingFormSet):
    def __init__(self, *args, studio=None, **kwargs):
        self.studio = studio
        super().__init__(*args, **kwargs)

        for form in self.forms:
            if studio is not None and "room" in form.fields:
                form.fields["room"].queryset = (
                    StudioRoom.objects
                    .filter(
                        studio=studio,
                        is_active=True,
                    )
                    .select_related(
                        "location",
                    )
                    .order_by(
                        "location__name",
                        "name",
                    )
                )

                form.fields["room"].required = False
                form.fields["room"].empty_label = "Select a room"
