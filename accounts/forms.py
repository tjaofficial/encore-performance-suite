from django import forms
from django.contrib.auth import authenticate


class EncoreLoginForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(
            attrs={
                "placeholder": "you@example.com",
                "autocomplete": "email",
            }
        )
    )

    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                "placeholder": "Password",
                "autocomplete": "current-password",
            }
        )
    )

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request
        self.user_cache = None

    def clean(self):
        cleaned_data = super().clean()

        email = cleaned_data.get("email")
        password = cleaned_data.get("password")

        if email and password:
            self.user_cache = authenticate(
                self.request,
                username=email,
                password=password,
            )

            if self.user_cache is None:
                raise forms.ValidationError(
                    "The email or password you entered is incorrect."
                )

            if not self.user_cache.is_active:
                raise forms.ValidationError(
                    "This account is inactive."
                )

        return cleaned_data

    def get_user(self):
        return self.user_cache


class StudioOwnerRegistrationForm(forms.Form):
    PLAN_CHOICES = [
        ("essentials", "Essentials"),
        ("pro", "Pro"),
    ]

    PAYMENT_MODE_CHOICES = [
        (
            "software_only",
            "Software Only",
        ),
        (
            "software_payments",
            "Software + Payments",
        ),
    ]

    first_name = forms.CharField(
        max_length=100,
    )

    last_name = forms.CharField(
        max_length=100,
    )

    email = forms.EmailField()

    password = forms.CharField(
        min_length=8,
        label="Password",
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "new-password",
            }
        ),
    )

    password_confirm = forms.CharField(
        min_length=8,
        label="Confirm Password",
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "new-password",
            }
        ),
    )

    studio_name = forms.CharField(
        max_length=255,
    )

    studio_email = forms.EmailField(
        required=False,
    )

    studio_phone = forms.CharField(
        max_length=50,
        required=False,
    )

    plan_tier = forms.ChoiceField(
        choices=PLAN_CHOICES,
        initial="pro",
    )

    payment_mode = forms.ChoiceField(
        choices=PAYMENT_MODE_CHOICES,
        initial="software_only",
    )

    drawing_board_enabled = forms.BooleanField(
        required=False,
        label="Add Drawing Board for $39/month",
    )

    agree_to_terms = forms.BooleanField(
        required=True,
        label=(
            "I agree to Encore's subscription terms "
            "and recurring monthly billing."
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(
            *args,
            **kwargs,
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

    def clean(self):
        cleaned_data = super().clean()

        password = cleaned_data.get(
            "password"
        )

        password_confirm = cleaned_data.get(
            "password_confirm"
        )

        if (
            password
            and password_confirm
            and password != password_confirm
        ):
            self.add_error(
                "password_confirm",
                "Passwords do not match.",
            )

        return cleaned_data

    def clean_email(self):
        email = self.cleaned_data[
            "email"
        ].strip().lower()

        from django.contrib.auth import get_user_model

        User = get_user_model()

        if User.objects.filter(
            email=email,
        ).exists():
            raise forms.ValidationError(
                (
                    "An Encore account already uses this email. "
                    "Sign in instead."
                )
            )

        return email
