from django import forms
from django.utils import timezone

import bleach
from bleach.css_sanitizer import CSSSanitizer

from classes.models import Class
from registration_portal.models import RegistrationPolicy


ALLOWED_TAGS = [
    "p", "br", "strong", "b", "em", "i", "u", "s",
    "h2", "h3", "h4", "blockquote", "ul", "ol", "li",
    "a", "span", "div", "font",
]
ALLOWED_ATTRIBUTES = {
    "a": ["href", "title", "target", "rel"],
    "span": ["style"],
    "div": ["style"],
    "p": ["style"],
    "h2": ["style"],
    "h3": ["style"],
    "h4": ["style"],
    "font": ["face", "size", "color"],
}
CSS_SANITIZER = CSSSanitizer(
    allowed_css_properties=[
        "text-align",
        "font-family",
        "font-size",
        "color",
    ]
)


class RegistrationPolicyForm(forms.ModelForm):
    classes = forms.ModelMultipleChoiceField(
        queryset=Class.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Select the classes that should trigger this policy.",
    )

    class Meta:
        model = RegistrationPolicy
        fields = [
            "title",
            "document_type",
            "content_html",
            "acceptance_text",
            "scope",
            "classes",
            "requires_signature",
            "is_active",
            "effective_date",
            "display_order",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": "encore-input", "placeholder": "Payment Policy"}),
            "document_type": forms.Select(attrs={"class": "encore-input"}),
            "content_html": forms.HiddenInput(attrs={"data-policy-html-input": "1"}),
            "acceptance_text": forms.TextInput(attrs={
                "class": "encore-input",
                "placeholder": "I have read and agree to the Payment Policy.",
            }),
            "scope": forms.Select(attrs={"class": "encore-input", "data-policy-scope": "1"}),
            "requires_signature": forms.CheckboxInput(attrs={"class": "encore-checkbox"}),
            "is_active": forms.CheckboxInput(attrs={"class": "encore-checkbox"}),
            "effective_date": forms.DateInput(attrs={"class": "encore-input", "type": "date"}),
            "display_order": forms.NumberInput(attrs={"class": "encore-input", "min": "0"}),
        }

    def __init__(self, *args, studio=None, **kwargs):
        self.studio = studio
        super().__init__(*args, **kwargs)
        if studio is not None:
            self.fields["classes"].queryset = (
                Class.objects.filter(studio=studio, is_active=True)
                .select_related("season", "class_type")
                .order_by("season__start_date", "name", "class_id")
            )

        self.fields["content_html"].required = True
        self.fields["acceptance_text"].required = False
        self.fields["effective_date"].required = False
        self.fields["display_order"].required = False
        self.fields["display_order"].initial = self.initial.get("display_order", 0)

    def clean_content_html(self):
        raw = str(self.cleaned_data.get("content_html") or "").strip()
        cleaned = bleach.clean(
            raw,
            tags=ALLOWED_TAGS,
            attributes=ALLOWED_ATTRIBUTES,
            protocols=["http", "https", "mailto", "tel"],
            css_sanitizer=CSS_SANITIZER,
            strip=True,
        ).strip()
        text_only = bleach.clean(cleaned, tags=[], strip=True).strip()
        if not text_only:
            raise forms.ValidationError("Add the policy or agreement text.")
        return cleaned

    def clean_acceptance_text(self):
        return str(self.cleaned_data.get("acceptance_text") or "").strip()

    def clean(self):
        cleaned = super().clean()
        scope = cleaned.get("scope")
        classes = cleaned.get("classes")
        if scope == RegistrationPolicy.Scope.SPECIFIC_CLASSES and not classes:
            self.add_error(
                "classes",
                "Choose at least one class for a class-specific policy.",
            )
        return cleaned
