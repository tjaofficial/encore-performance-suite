import re
from urllib.parse import urlparse

from django import forms


class PublicContactForm(forms.Form):
    class ContactReason:
        DEMO = "demo"
        SALES = "sales"
        MIGRATION = "migration"
        SUPPORT = "support"
        BILLING = "billing"
        TECHNICAL = "technical"
        OTHER = "other"

        CHOICES = [
            (DEMO, "Demo / Product Walkthrough"),
            (SALES, "Sales / Plan Question"),
            (MIGRATION, "Onboarding / Migration"),
            (SUPPORT, "Existing Customer Support"),
            (BILLING, "Billing Question"),
            (TECHNICAL, "Technical Question"),
            (OTHER, "Other"),
        ]

    name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(
            attrs={
                "class": "contact-input",
                "autocomplete": "name",
                "placeholder": "Your name",
            }
        ),
    )

    studio_name = forms.CharField(
        max_length=180,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "contact-input",
                "autocomplete": "organization",
                "placeholder": "Studio name",
            }
        ),
    )

    email = forms.EmailField(
        max_length=254,
        widget=forms.EmailInput(
            attrs={
                "class": "contact-input",
                "autocomplete": "email",
                "placeholder": "you@example.com",
            }
        ),
    )

    phone = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "contact-input",
                "autocomplete": "tel",
                "placeholder": "Optional",
            }
        ),
    )

    reason = forms.ChoiceField(
        choices=ContactReason.CHOICES,
        widget=forms.Select(
            attrs={
                "class": "contact-input",
            }
        ),
    )

    message = forms.CharField(
        max_length=5000,
        min_length=10,
        widget=forms.Textarea(
            attrs={
                "class": "contact-input contact-textarea",
                "rows": 7,
                "placeholder": "How can we help?",
            }
        ),
    )

    # Honeypot. Real users never see or fill this field.
    website = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={
                "tabindex": "-1",
                "autocomplete": "off",
            }
        ),
    )

    def clean_name(self):
        value = self.cleaned_data["name"].strip()

        if len(value) < 2:
            raise forms.ValidationError(
                "Please enter your name."
            )

        return value

    def clean_studio_name(self):
        return self.cleaned_data["studio_name"].strip()

    def clean_phone(self):
        return self.cleaned_data["phone"].strip()

    def clean_message(self):
        return self.cleaned_data["message"].strip()

    @property
    def reason_label(self):
        return dict(
            self.ContactReason.CHOICES
        ).get(
            self.cleaned_data.get("reason"),
            "Contact Request",
        )
