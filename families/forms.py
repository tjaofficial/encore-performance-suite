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


PARENT_STATE_CHOICES = [
    ("", "Select a state"),
    ("AL", "Alabama"), ("AK", "Alaska"), ("AZ", "Arizona"),
    ("AR", "Arkansas"), ("CA", "California"), ("CO", "Colorado"),
    ("CT", "Connecticut"), ("DE", "Delaware"), ("FL", "Florida"),
    ("GA", "Georgia"), ("HI", "Hawaii"), ("ID", "Idaho"),
    ("IL", "Illinois"), ("IN", "Indiana"), ("IA", "Iowa"),
    ("KS", "Kansas"), ("KY", "Kentucky"), ("LA", "Louisiana"),
    ("ME", "Maine"), ("MD", "Maryland"), ("MA", "Massachusetts"),
    ("MI", "Michigan"), ("MN", "Minnesota"), ("MS", "Mississippi"),
    ("MO", "Missouri"), ("MT", "Montana"), ("NE", "Nebraska"),
    ("NV", "Nevada"), ("NH", "New Hampshire"), ("NJ", "New Jersey"),
    ("NM", "New Mexico"), ("NY", "New York"), ("NC", "North Carolina"),
    ("ND", "North Dakota"), ("OH", "Ohio"), ("OK", "Oklahoma"),
    ("OR", "Oregon"), ("PA", "Pennsylvania"), ("RI", "Rhode Island"),
    ("SC", "South Carolina"), ("SD", "South Dakota"), ("TN", "Tennessee"),
    ("TX", "Texas"), ("UT", "Utah"), ("VT", "Vermont"),
    ("VA", "Virginia"), ("WA", "Washington"), ("WV", "West Virginia"),
    ("WI", "Wisconsin"), ("WY", "Wyoming"), ("DC", "District of Columbia"),
]


class ParentFamilyForm(forms.ModelForm):
    state = forms.ChoiceField(
        choices=PARENT_STATE_CHOICES,
        required=False,
        label="State",
    )

    class Meta:
        model = Family
        fields = [
            "family_name",
            "primary_email",
            "secondary_email",
            "primary_phone",
            "secondary_phone",
            "address_line_1",
            "address_line_2",
            "city",
            "state",
            "postal_code",
            "emergency_contact_name",
            "emergency_contact_phone",
            "emergency_contact_relationship",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        current_state = str(
            getattr(self.instance, "state", "") or ""
        ).strip()

        if current_state and len(current_state) != 2:
            for value, label in PARENT_STATE_CHOICES:
                if label.lower() == current_state.lower():
                    self.initial["state"] = value
                    break

        for field in self.fields.values():
            field.widget.attrs["class"] = "parent-input"


class ParentGuardianProfileForm(forms.ModelForm):
    class Meta:
        model = Guardian
        fields = [
            "first_name",
            "last_name",
            "relationship",
            "email",
            "phone",
            "is_authorized_for_pickup",
            "is_financially_responsible",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "parent-checkbox"
            else:
                field.widget.attrs["class"] = "parent-input"


class ParentGuardianInviteForm(forms.Form):
    first_name = forms.CharField(max_length=100)
    last_name = forms.CharField(max_length=100)
    relationship = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(
            attrs={"placeholder": "Parent, guardian, grandparent..."}
        ),
    )
    email = forms.EmailField()
    phone = forms.CharField(max_length=50, required=False)
    is_authorized_for_pickup = forms.BooleanField(
        required=False,
        initial=True,
        label="Authorized for pickup",
    )
    is_financially_responsible = forms.BooleanField(
        required=False,
        label="Financially responsible",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "parent-checkbox"
            else:
                field.widget.attrs["class"] = "parent-input"
