from datetime import date
from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.hashers import make_password

from classes.models import Class
from .models import FamilyInvite, RegistrationRequest, PublicRegistrationSession

US_STATE_CHOICES = [
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

STATE_NAME_TO_ABBREVIATION = {label.lower(): value for value, label in US_STATE_CHOICES if value}


class PublicRegistrationRequestForm(forms.ModelForm):
    class Meta:
        model = RegistrationRequest
        fields = [
            "guardian_first_name",
            "guardian_last_name",
            "email",
            "phone",
            "student_first_name",
            "student_last_name",
            "student_birthday",
            "notes",
        ]

        labels = {
            "guardian_first_name": "Parent / Guardian First Name",
            "guardian_last_name": "Parent / Guardian Last Name",
            "email": "Email",
            "phone": "Phone",
            "student_first_name": "Student First Name",
            "student_last_name": "Student Last Name",
            "student_birthday": "Student Birthday",
            "notes": "Anything the studio should know?",
        }

        widgets = {
            "student_birthday": forms.DateInput(
                attrs={"type": "date"}
            ),
            "notes": forms.Textarea(
                attrs={"rows": 4}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field in self.fields.values():
            field.widget.attrs["class"] = "public-input"


class NewFamilyAccountForm(forms.Form):
    email = forms.EmailField(
        disabled=True,
    )

    password1 = forms.CharField(
        label="Create Password",
        widget=forms.PasswordInput(),
    )

    password2 = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput(),
    )

    terms = forms.BooleanField(
        label=(
            "I agree to create an Encore account "
            "for this registration."
        )
    )

    def __init__(
        self,
        *args,
        email=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self.fields["email"].initial = email

        for field in self.fields.values():
            if isinstance(
                field.widget,
                forms.CheckboxInput,
            ):
                field.widget.attrs[
                    "class"
                ] = "public-checkbox"
            else:
                field.widget.attrs[
                    "class"
                ] = "public-input"

    def clean(self):
        cleaned = super().clean()

        password1 = cleaned.get(
            "password1"
        )

        password2 = cleaned.get(
            "password2"
        )

        if (
            password1
            and password2
            and password1 != password2
        ):
            self.add_error(
                "password2",
                "Passwords do not match.",
            )

        if password1:
            try:
                validate_password(
                    password1
                )
            except ValidationError as exc:
                self.add_error(
                    "password1",
                    exc,
                )

        return cleaned


class FamilyInviteForm(forms.ModelForm):
    class Meta:
        model = FamilyInvite
        fields = [
            "email",
            "guardian_first_name",
            "guardian_last_name",
            "family",
        ]

    def __init__(
        self,
        *args,
        studio=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        if studio is not None:
            self.fields[
                "family"
            ].queryset = (
                self.fields[
                    "family"
                ].queryset.filter(
                    studio=studio,
                )
            )

        for field in self.fields.values():
            field.widget.attrs[
                "class"
            ] = "encore-input"


class AcceptInviteForm(forms.Form):
    password1 = forms.CharField(
        label="Create Password",
        widget=forms.PasswordInput(),
    )

    password2 = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput(),
    )

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
            ] = "public-input"

    def clean(self):
        cleaned = super().clean()

        p1 = cleaned.get("password1")
        p2 = cleaned.get("password2")

        if p1 and p2 and p1 != p2:
            self.add_error(
                "password2",
                "Passwords do not match.",
            )

        if p1:
            try:
                validate_password(p1)
            except ValidationError as exc:
                self.add_error(
                    "password1",
                    exc,
                )

        return cleaned


def _age_from_birthday(birthday):
    today = date.today()

    return (
        today.year
        - birthday.year
        - (
            (today.month, today.day)
            < (birthday.month, birthday.day)
        )
    )


def _validate_new_email(
    form,
    field_name,
    *,
    exclude_email="",
):
    value = (
        form.cleaned_data.get(field_name)
        or ""
    ).strip().lower()

    if not value:
        return

    if (
        exclude_email
        and value == exclude_email.strip().lower()
    ):
        form.add_error(
            field_name,
            "Use a different email address for the student login.",
        )
        return

    User = get_user_model()

    if User.objects.filter(
        email__iexact=value,
    ).exists():
        form.add_error(
            field_name,
            (
                "An Encore account already uses this email. "
                "Use a different email for the student's separate login."
            ),
        )


class RegistrationTypeForm(forms.Form):
    registration_type = forms.ChoiceField(
        label="Who are you registering?",
        choices=PublicRegistrationSession.RegistrationType.choices,
        widget=forms.RadioSelect,
    )


class ExistingAccountLoginForm(forms.Form):
    email = forms.EmailField(
        label="Encore Email",
    )
    password = forms.CharField(
        label="Encore Password",
        widget=forms.PasswordInput(),
    )

    def __init__(
        self,
        *args,
        request=None,
        **kwargs,
    ):
        self.request = request
        self.user = None

        super().__init__(
            *args,
            **kwargs,
        )

        for field in self.fields.values():
            field.widget.attrs["class"] = "public-input"

    def clean(self):
        cleaned = super().clean()

        email = (
            cleaned.get("email")
            or ""
        ).strip().lower()

        password = cleaned.get(
            "password"
        )

        if not email or not password:
            return cleaned

        user = authenticate(
            self.request,
            username=email,
            password=password,
        )

        if user is None:
            raise ValidationError(
                "The email or password is incorrect."
            )

        if not user.is_active:
            raise ValidationError(
                "This Encore account is inactive."
            )

        self.user = user
        return cleaned


class GuardianAccountDetailsForm(forms.Form):
    guardian_first_name = forms.CharField(
        max_length=100,
        label="Parent / Guardian First Name",
    )
    guardian_last_name = forms.CharField(
        max_length=100,
        label="Parent / Guardian Last Name",
    )
    guardian_relationship = forms.CharField(
        max_length=100,
        label="Relationship to Student",
        required=False,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Parent, guardian, grandparent..."
            }
        ),
    )
    email = forms.EmailField(
        label="Parent / Guardian Email",
    )
    phone = forms.CharField(
        max_length=50,
        required=False,
        label="Phone",
    )
    password1 = forms.CharField(
        label="Create Encore Password",
        widget=forms.PasswordInput(),
    )
    password2 = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput(),
    )

    family_name = forms.CharField(
        max_length=255,
        required=False,
        label="Household / Family Name",
        widget=forms.TextInput(
            attrs={
                "placeholder": "Example: Smith Family"
            }
        ),
    )
    address_line_1 = forms.CharField(
        max_length=255,
        required=False,
        label="Address",
    )
    address_line_2 = forms.CharField(
        max_length=255,
        required=False,
        label="Address Line 2",
    )
    city = forms.CharField(
        max_length=100,
        required=False,
    )
    state = forms.ChoiceField(
        choices=US_STATE_CHOICES,
        required=False,
        label="State",
    )
    postal_code = forms.CharField(
        max_length=20,
        required=False,
        label="ZIP / Postal Code",
    )

    emergency_contact_name = forms.CharField(
        max_length=255,
        required=False,
    )
    emergency_contact_phone = forms.CharField(
        max_length=50,
        required=False,
    )
    emergency_contact_relationship = forms.CharField(
        max_length=100,
        required=False,
    )
    how_did_you_hear_about_us = forms.CharField(
        max_length=255,
        required=False,
        label="How did you hear about the studio?",
    )

    def __init__(
        self,
        *args,
        saved_data=None,
        **kwargs,
    ):
        initial = dict(saved_data or {})
        saved_state = str(initial.get("state") or "").strip()
        if saved_state and len(saved_state) != 2:
            initial["state"] = STATE_NAME_TO_ABBREVIATION.get(
                saved_state.lower(),
                saved_state,
            )

        super().__init__(
            *args,
            initial=initial or None,
            **kwargs,
        )

        for field in self.fields.values():
            field.widget.attrs["class"] = "public-input"

    def clean_email(self):
        email = self.cleaned_data["email"]

        User = get_user_model()

        if User.objects.filter(
            email__iexact=email,
        ).exists():
            raise ValidationError(
                (
                    "An Encore account already uses this email. "
                    "For now, use a new email while we finish "
                    "the existing-account resume flow."
                )
            )

        return email

    def clean(self):
        cleaned = super().clean()

        p1 = cleaned.get("password1")
        p2 = cleaned.get("password2")

        if p1 and p2 and p1 != p2:
            self.add_error(
                "password2",
                "Passwords do not match.",
            )

        if p1:
            try:
                validate_password(p1)
            except ValidationError as exc:
                self.add_error(
                    "password1",
                    exc,
                )

        return cleaned

    def serialized_data(self):
        data = dict(self.cleaned_data)

        password = data.pop(
            "password1",
        )
        data.pop(
            "password2",
            None,
        )
        data["password_hash"] = make_password(
            password
        )

        return data


class SelfAccountDetailsForm(forms.Form):
    first_name = forms.CharField(
        max_length=100,
    )
    last_name = forms.CharField(
        max_length=100,
    )
    email = forms.EmailField()
    phone = forms.CharField(
        max_length=50,
        required=False,
    )
    password1 = forms.CharField(
        label="Create Encore Password",
        widget=forms.PasswordInput(),
    )
    password2 = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput(),
    )

    address_line_1 = forms.CharField(
        max_length=255,
        required=False,
        label="Address",
    )
    address_line_2 = forms.CharField(
        max_length=255,
        required=False,
        label="Address Line 2",
    )
    city = forms.CharField(
        max_length=100,
        required=False,
    )
    state = forms.ChoiceField(
        choices=US_STATE_CHOICES,
        required=False,
        label="State",
    )
    postal_code = forms.CharField(
        max_length=20,
        required=False,
        label="ZIP / Postal Code",
    )
    emergency_contact_name = forms.CharField(
        max_length=255,
        required=False,
    )
    emergency_contact_phone = forms.CharField(
        max_length=50,
        required=False,
    )
    emergency_contact_relationship = forms.CharField(
        max_length=100,
        required=False,
    )
    how_did_you_hear_about_us = forms.CharField(
        max_length=255,
        required=False,
        label="How did you hear about the studio?",
    )

    def __init__(
        self,
        *args,
        saved_data=None,
        **kwargs,
    ):
        initial = dict(saved_data or {})
        saved_state = str(initial.get("state") or "").strip()
        if saved_state and len(saved_state) != 2:
            initial["state"] = STATE_NAME_TO_ABBREVIATION.get(
                saved_state.lower(),
                saved_state,
            )

        super().__init__(
            *args,
            initial=initial or None,
            **kwargs,
        )

        for field in self.fields.values():
            field.widget.attrs["class"] = "public-input"

    def clean_email(self):
        email = self.cleaned_data["email"]

        User = get_user_model()

        if User.objects.filter(
            email__iexact=email,
        ).exists():
            raise ValidationError(
                (
                    "An Encore account already uses this email. "
                    "For now, use a new email while we finish "
                    "the existing-account resume flow."
                )
            )

        return email

    def clean(self):
        cleaned = super().clean()

        p1 = cleaned.get("password1")
        p2 = cleaned.get("password2")

        if p1 and p2 and p1 != p2:
            self.add_error(
                "password2",
                "Passwords do not match.",
            )

        if p1:
            try:
                validate_password(p1)
            except ValidationError as exc:
                self.add_error(
                    "password1",
                    exc,
                )

        return cleaned

    def serialized_data(self):
        data = dict(self.cleaned_data)

        password = data.pop(
            "password1",
        )
        data.pop(
            "password2",
            None,
        )
        data["password_hash"] = make_password(
            password
        )

        return data


class StudentDetailsForm(forms.Form):
    student_first_name = forms.CharField(
        max_length=100,
        label="Student First Name",
        required=False,
    )
    student_last_name = forms.CharField(
        max_length=100,
        label="Student Last Name",
        required=False,
    )
    birthday = forms.DateField(
        label="Birthday",
        widget=forms.DateInput(
            attrs={
                "type": "date",
                "class": "public-input",
            }
        ),
    )
    gender = forms.ChoiceField(
        required=False,
        choices=[
            ("", "Prefer not to say"),
            ("female", "Female"),
            ("male", "Male"),
        ],
    )
    medical_conditions = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={"rows": 3}
        ),
    )
    allergies = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={"rows": 3}
        ),
    )
    comments = forms.CharField(
        required=False,
        label="Anything else the studio should know?",
        widget=forms.Textarea(
            attrs={"rows": 3}
        ),
    )

    create_student_login = forms.BooleanField(
        required=False,
        label="Create a separate Encore login for this student",
    )
    student_email = forms.EmailField(
        required=False,
        label="Student Email",
    )
    student_password1 = forms.CharField(
        required=False,
        label="Student Password",
        widget=forms.PasswordInput(),
    )
    student_password2 = forms.CharField(
        required=False,
        label="Confirm Student Password",
        widget=forms.PasswordInput(),
    )

    def __init__(
        self,
        *args,
        registration_type,
        account_email="",
        account_data=None,
        saved_data=None,
        **kwargs,
    ):
        self.registration_type = registration_type
        self.account_email = account_email
        self.account_data = account_data or {}

        initial = dict(saved_data or {})

        if registration_type == PublicRegistrationSession.RegistrationType.SELF:
            initial.setdefault(
                "student_first_name",
                self.account_data.get(
                    "first_name",
                    "",
                ),
            )
            initial.setdefault(
                "student_last_name",
                self.account_data.get(
                    "last_name",
                    "",
                ),
            )

        super().__init__(
            *args,
            initial=initial or None,
            **kwargs,
        )

        if registration_type == PublicRegistrationSession.RegistrationType.SELF:
            self.fields[
                "student_first_name"
            ].widget = forms.HiddenInput()
            self.fields[
                "student_last_name"
            ].widget = forms.HiddenInput()

            self.fields.pop(
                "create_student_login"
            )
            self.fields.pop(
                "student_email"
            )
            self.fields.pop(
                "student_password1"
            )
            self.fields.pop(
                "student_password2"
            )

        for field in self.fields.values():
            if isinstance(
                field.widget,
                forms.CheckboxInput,
            ):
                field.widget.attrs[
                    "class"
                ] = "public-checkbox"
            elif not isinstance(
                field.widget,
                forms.HiddenInput,
            ):
                existing = field.widget.attrs.get(
                    "class",
                    "",
                )
                if "public-input" not in existing:
                    field.widget.attrs[
                        "class"
                    ] = (
                        f"{existing} public-input"
                    ).strip()

    def clean(self):
        cleaned = super().clean()

        birthday = cleaned.get(
            "birthday"
        )

        if not birthday:
            return cleaned

        age = _age_from_birthday(
            birthday
        )

        if (
            self.registration_type
            == PublicRegistrationSession.RegistrationType.SELF
            and age < 18
        ):
            self.add_error(
                "birthday",
                (
                    "Self-registration is for adult students age 18 or older. "
                    "A parent or guardian must register students under 18."
                ),
            )

        if (
            self.registration_type
            == PublicRegistrationSession.RegistrationType.STUDENT
            and not cleaned.get("student_first_name")
        ):
            self.add_error(
                "student_first_name",
                "Enter the student's first name.",
            )

        if (
            self.registration_type
            == PublicRegistrationSession.RegistrationType.STUDENT
            and not cleaned.get("student_last_name")
        ):
            self.add_error(
                "student_last_name",
                "Enter the student's last name.",
            )

        create_login = cleaned.get(
            "create_student_login",
            False,
        )

        if create_login:
            if age < 14:
                self.add_error(
                    "create_student_login",
                    (
                        "A separate student login is available "
                        "for students age 14 or older."
                    ),
                )

            email = cleaned.get(
                "student_email"
            )
            p1 = cleaned.get(
                "student_password1"
            )
            p2 = cleaned.get(
                "student_password2"
            )

            if not email:
                self.add_error(
                    "student_email",
                    "Enter an email for the student login.",
                )
            else:
                _validate_new_email(
                    self,
                    "student_email",
                    exclude_email=self.account_email,
                )

            if not p1:
                self.add_error(
                    "student_password1",
                    "Create a password for the student.",
                )

            if p1 and p2 and p1 != p2:
                self.add_error(
                    "student_password2",
                    "Passwords do not match.",
                )

            if not p2:
                self.add_error(
                    "student_password2",
                    "Confirm the student's password.",
                )

            if p1:
                try:
                    validate_password(p1)
                except ValidationError as exc:
                    self.add_error(
                        "student_password1",
                        exc,
                    )

        return cleaned

    def serialized_data(self):
        data = dict(self.cleaned_data)

        if data.get(
            "create_student_login"
        ):
            password = data.pop(
                "student_password1",
            )
            data.pop(
                "student_password2",
                None,
            )
            data[
                "student_password_hash"
            ] = make_password(
                password
            )
        else:
            data.pop(
                "student_password1",
                None,
            )
            data.pop(
                "student_password2",
                None,
            )
            data.pop(
                "student_email",
                None,
            )

        return data


class ClassSelectionForm(forms.Form):
    classes = forms.ModelMultipleChoiceField(
        queryset=Class.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        label="Select Classes",
    )

    def __init__(
        self,
        *args,
        queryset,
        selected_ids=None,
        **kwargs,
    ):
        super().__init__(
            *args,
            **kwargs,
        )

        self.fields[
            "classes"
        ].queryset = queryset

        if selected_ids:
            self.fields[
                "classes"
            ].initial = selected_ids


class RegistrationReviewForm(forms.Form):
    confirm = forms.BooleanField(
        required=True,
        label=(
            "I confirm that the registration information "
            "and selected classes are correct."
        ),
    )
