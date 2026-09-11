from django import forms

from classes.models import ClassType, Season
from studios.models import (
    Studio,
    StudioLocation,
    StudioRoom,
    StudioSettings,
)


class StudioProfileForm(forms.ModelForm):
    class Meta:
        model = Studio
        fields = [
            "name",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field in self.fields.values():
            field.widget.attrs["class"] = "encore-input"


class StudioBrandingForm(forms.ModelForm):
    class Meta:
        model = StudioSettings
        fields = [
            "logo",
            "primary_color",
            "accent_color",
            "public_registration_enabled",
            "show_capacity_publicly",
            "allow_waitlist_requests",
        ]

        widgets = {
            "primary_color": forms.TextInput(
                attrs={
                    "type": "color",
                    "class": "encore-color-input",
                }
            ),
            "accent_color": forms.TextInput(
                attrs={
                    "type": "color",
                    "class": "encore-color-input",
                }
            ),
        }

        labels = {
            "logo": "Studio Logo",
            "primary_color": "Primary Color",
            "accent_color": "Accent Color",
            "public_registration_enabled": "Public Registration Enabled",
            "show_capacity_publicly": "Show Capacity Publicly",
            "allow_waitlist_requests": "Allow Waitlist Requests",
        }

        help_texts = {
            "logo": "Shown in the studio portal and public registration experience.",
            "primary_color": "Main studio brand color.",
            "accent_color": "Secondary highlight color.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "encore-checkbox"
            elif name not in {
                "primary_color",
                "accent_color",
            }:
                field.widget.attrs["class"] = "encore-input"


class StudioLocationForm(forms.ModelForm):
    class Meta:
        model = StudioLocation
        exclude = [
            "studio",
        ]

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


class StudioRoomForm(forms.ModelForm):
    class Meta:
        model = StudioRoom
        fields = [
            "location",
            "name",
            "capacity",
            "notes",
            "is_active",
        ]

        widgets = {
            "name": forms.TextInput(
                attrs={
                    "placeholder": "Example: Studio A",
                }
            ),
            "capacity": forms.NumberInput(
                attrs={
                    "min": 1,
                    "step": 1,
                    "placeholder": "Optional",
                }
            ),
            "notes": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": (
                        "Optional notes about flooring, mirrors, "
                        "equipment, or room use."
                    ),
                }
            ),
        }

        labels = {
            "location": "Physical Location (Optional)",
            "name": "Room Name",
            "capacity": "Room Capacity",
            "notes": "Room Notes",
            "is_active": "Active",
        }

    def __init__(
        self,
        *args,
        studio=None,
        **kwargs,
    ):
        super().__init__(
            *args,
            **kwargs,
        )

        self.fields[
            "location"
        ].required = False

        self.fields[
            "location"
        ].empty_label = (
            "No physical location — studio room"
        )

        self.fields[
            "location"
        ].help_text = (
            "Leave this blank for a room that belongs directly "
            "to the studio. Choose a location only when this room "
            "is inside a specific building or site."
        )

        if studio is not None:
            self.fields[
                "location"
            ].queryset = (
                StudioLocation.objects
                .filter(
                    studio=studio,
                    is_active=True,
                )
                .order_by(
                    "-is_primary",
                    "name",
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


class SeasonForm(forms.ModelForm):
    class Meta:
        model = Season
        exclude = [
            "studio",
        ]

        widgets = {
            "start_date": forms.DateInput(
                attrs={"type": "date"}
            ),
            "end_date": forms.DateInput(
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


class ClassTypeForm(forms.ModelForm):
    class Meta:
        model = ClassType
        exclude = [
            "studio",
        ]

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


class StaffInviteForm(forms.Form):
    ROLE_CHOICES = [
        ("administrator", "Administrator"),
        ("teacher", "Teacher"),
    ]

    first_name = forms.CharField(
        max_length=100,
    )

    last_name = forms.CharField(
        max_length=100,
    )

    email = forms.EmailField()

    role = forms.ChoiceField(
        choices=ROLE_CHOICES,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field in self.fields.values():
            field.widget.attrs[
                "class"
            ] = "encore-input"


class PublicWidgetSettingsForm(forms.Form):
    STYLE_CHOICES = [
        ("clean", "Clean"),
        ("cards", "Cards"),
        ("minimal", "Minimal"),
    ]

    CALENDAR_STYLE_CHOICES = [
        ("month", "Month Calendar"),
        ("agenda", "Agenda"),
        ("compact", "Compact"),
    ]

    calendar_enabled = forms.BooleanField(
        required=False,
        label="Enable Calendar Widget",
    )
    calendar_style = forms.ChoiceField(
        choices=CALENDAR_STYLE_CHOICES,
        label="Calendar Style",
    )
    calendar_show_details = forms.BooleanField(
        required=False,
        label="Show Event Details",
    )

    classes_enabled = forms.BooleanField(
        required=False,
        label="Enable Classes Widget",
    )
    classes_style = forms.ChoiceField(
        choices=STYLE_CHOICES,
        label="Classes Style",
    )
    default_season = forms.ModelChoiceField(
        queryset=Season.objects.none(),
        required=False,
        label="Default Season",
        empty_label="All Active Seasons",
    )
    show_class_pricing = forms.BooleanField(
        required=False,
        label="Show Tuition",
    )
    show_class_capacity = forms.BooleanField(
        required=False,
        label="Show Capacity",
    )

    registration_enabled = forms.BooleanField(
        required=False,
        label="Enable Registration Widget",
    )
    registration_style = forms.ChoiceField(
        choices=STYLE_CHOICES,
        label="Registration Style",
    )

    def __init__(
        self,
        *args,
        studio=None,
        settings_obj=None,
        **kwargs,
    ):
        self.studio = studio
        self.settings_obj = settings_obj
        stored = (
            dict(settings_obj.public_widget_settings or {})
            if settings_obj is not None
            else {}
        )

        defaults = {
            "calendar_enabled": True,
            "calendar_style": "month",
            "calendar_show_details": True,
            "classes_enabled": True,
            "classes_style": "cards",
            "default_season": None,
            "show_class_pricing": True,
            "show_class_capacity": True,
            "registration_enabled": True,
            "registration_style": "clean",
        }
        defaults.update(stored)

        super().__init__(
            *args,
            initial=defaults,
            **kwargs,
        )

        self.fields["default_season"].queryset = (
            Season.objects
            .filter(
                studio=studio,
                is_active=True,
            )
            .order_by(
                "-start_date",
                "name",
            )
            if studio is not None
            else Season.objects.none()
        )

        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "encore-checkbox"
            else:
                field.widget.attrs["class"] = "encore-input"

    def save(self):
        if self.settings_obj is None:
            raise ValueError(
                "Widget settings require a StudioSettings instance."
            )

        season = self.cleaned_data.get(
            "default_season"
        )

        self.settings_obj.public_widget_settings = {
            "calendar_enabled": self.cleaned_data[
                "calendar_enabled"
            ],
            "calendar_style": self.cleaned_data[
                "calendar_style"
            ],
            "calendar_show_details": self.cleaned_data[
                "calendar_show_details"
            ],
            "classes_enabled": self.cleaned_data[
                "classes_enabled"
            ],
            "classes_style": self.cleaned_data[
                "classes_style"
            ],
            "default_season": (
                season.pk if season else None
            ),
            "show_class_pricing": self.cleaned_data[
                "show_class_pricing"
            ],
            "show_class_capacity": self.cleaned_data[
                "show_class_capacity"
            ],
            "registration_enabled": self.cleaned_data[
                "registration_enabled"
            ],
            "registration_style": self.cleaned_data[
                "registration_style"
            ],
        }

        self.settings_obj.save(
            update_fields=[
                "public_widget_settings",
                "updated_at",
            ]
        )

        return self.settings_obj
