from django import forms

from .models import Instructor


class EncoreInstructorForm(forms.ModelForm):
    class Meta:
        model = Instructor
        exclude = [
            "studio",
            "user",
            "activation_token",
            "activation_sent_at",
            "activation_expires_at",
            "claimed_at",
            "profile_verified_at",
            "availability_completed_at",
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


class InstructorClaimProfileForm(forms.ModelForm):
    password1 = forms.CharField(
        required=False,
        label="Create Password",
        widget=forms.PasswordInput(
            attrs={
                "class": "encore-input",
                "autocomplete": "new-password",
            }
        ),
    )
    password2 = forms.CharField(
        required=False,
        label="Confirm Password",
        widget=forms.PasswordInput(
            attrs={
                "class": "encore-input",
                "autocomplete": "new-password",
            }
        ),
    )

    class Meta:
        model = Instructor
        fields = [
            "first_name",
            "last_name",
            "phone",
            "address_line_1",
            "address_line_2",
            "city",
            "state",
            "postal_code",
            "emergency_contact_name",
            "emergency_contact_phone",
            "emergency_contact_relationship",
            "bio",
        ]
        widgets = {
            "bio": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(
        self,
        *args,
        existing_user=None,
        **kwargs,
    ):
        self.existing_user = existing_user
        super().__init__(*args, **kwargs)

        for field in self.fields.values():
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = (
                f"{existing} encore-input".strip()
            )

        if existing_user is not None:
            self.fields["password1"].widget = forms.HiddenInput()
            self.fields["password2"].widget = forms.HiddenInput()
            self.fields["password1"].required = False
            self.fields["password2"].required = False
        else:
            self.fields["password1"].required = True
            self.fields["password2"].required = True

    def clean(self):
        cleaned = super().clean()

        if self.existing_user is None:
            password1 = cleaned.get("password1") or ""
            password2 = cleaned.get("password2") or ""

            if password1 != password2:
                self.add_error(
                    "password2",
                    "The passwords do not match.",
                )

            if password1 and len(password1) < 8:
                self.add_error(
                    "password1",
                    "Use at least 8 characters.",
                )

        return cleaned
