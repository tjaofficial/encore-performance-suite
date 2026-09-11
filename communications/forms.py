from django import forms
from django.db.models import Q

from classes.models import Class
from instructors.models import Instructor

from .models import (
    Announcement,
    AutomatedEmailSetting,
    EmailAutomationRule,
    EmailCampaign,
    EmailSignature,
    EmailTemplate,
)


class AnnouncementForm(forms.ModelForm):
    class Meta:
        model = Announcement
        fields = [
            "title",
            "message",
            "audience",
            "classes",
            "priority",
            "is_pinned",
            "is_published",
            "publish_at",
            "expires_at",
        ]

        widgets = {
            "message": forms.Textarea(
                attrs={"rows": 7}
            ),
            "publish_at": forms.DateTimeInput(
                attrs={"type": "datetime-local"}
            ),
            "expires_at": forms.DateTimeInput(
                attrs={"type": "datetime-local"}
            ),
            "classes": forms.SelectMultiple(
                attrs={"size": 8}
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

                # Teachers can send to their own classes or staff/teachers,
                # but not broadcast to every family/student in the studio.
                self.fields["audience"].choices = [
                    (
                        Announcement.Audience.CLASS,
                        "Specific Class(es)",
                    ),
                    (
                        Announcement.Audience.STAFF,
                        "All Staff",
                    ),
                    (
                        Announcement.Audience.TEACHERS,
                        "Teachers",
                    ),
                ]

            self.fields["classes"].queryset = (
                classes
                .select_related("season")
                .order_by("name")
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
                current = field.widget.attrs.get(
                    "class",
                    "",
                )
                field.widget.attrs[
                    "class"
                ] = (
                    f"{current} encore-input".strip()
                )

    def clean(self):
        cleaned = super().clean()

        audience = cleaned.get("audience")
        classes = cleaned.get("classes")

        if (
            audience == Announcement.Audience.CLASS
            and not classes
        ):
            self.add_error(
                "classes",
                "Choose at least one class for a class announcement.",
            )

        if (
            audience != Announcement.Audience.CLASS
            and classes
        ):
            self.add_error(
                "classes",
                (
                    "Class selection is only used when "
                    "Audience is Specific Class(es)."
                ),
            )

        return cleaned



class EmailSignatureForm(forms.ModelForm):
    class Meta:
        model = EmailSignature
        fields = [
            "name",
            "body",
            "is_default",
            "is_active",
        ]

        widgets = {
            "body": forms.Textarea(
                attrs={
                    "rows": 7,
                    "placeholder": (
                        "Thanks,\n"
                        "The Dance Place Team\n"
                        "(555) 555-5555"
                    ),
                }
            ),
        }

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


class EmailTemplateForm(forms.ModelForm):
    class Meta:
        model = EmailTemplate
        fields = [
            "name",
            "category",
            "subject",
            "html_body",
            "text_body",
            "signature",
            "is_active",
        ]

        labels = {
            "html_body": "Email Body",
            "text_body": "Plain Text Version",
        }

        help_texts = {
            "text_body": (
                "Optional. Encore can generate a plain-text version "
                "from the email body when this is left blank."
            ),
        }

        widgets = {
            "html_body": forms.Textarea(
                attrs={
                    "rows": 14,
                    "placeholder": "Write the email message here...",
                    "data-email-html-source": "true",
                }
            ),
            "text_body": forms.Textarea(attrs={"rows": 8}),
        }

    def __init__(self, *args, studio=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.use_required_attribute = False

        if studio is not None:
            self.fields["signature"].queryset = (
                EmailSignature.objects
                .filter(studio=studio, is_active=True)
                .order_by("-is_default", "name")
            )

        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "encore-checkbox"
            else:
                field.widget.attrs["class"] = "encore-input"


class EmailCampaignForm(forms.ModelForm):
    MESSAGE_SOURCE_CHOICES = [
        ("new", "New Email"),
        ("template", "Use Template"),
    ]

    message_source = forms.ChoiceField(
        choices=MESSAGE_SOURCE_CHOICES,
        initial="new",
        required=True,
        label="Message Source",
        widget=forms.RadioSelect,
    )

    schedule_email = forms.BooleanField(
        required=False,
        label="Schedule this email",
    )

    class Meta:
        model = EmailCampaign
        fields = [
            "name",
            "sender_type",
            "recipient_selection",
            "send_to_students",
            "template",
            "subject",
            "html_body",
            "text_body",
            "signature",
            "scheduled_for",
        ]

        labels = {
            "name": "Campaign Name",
            "sender_type": "Send From",
            "send_to_students": "Also send to student account emails",
            "html_body": "Email Body",
            "text_body": "Plain Text Version",
            "scheduled_for": "Schedule For",
        }

        widgets = {
            "recipient_selection": forms.HiddenInput(
                attrs={"data-recipient-selection": "true"}
            ),
            "html_body": forms.Textarea(
                attrs={
                    "rows": 14,
                    "placeholder": "Write your email...",
                    "data-email-html-source": "true",
                }
            ),
            "text_body": forms.Textarea(attrs={"rows": 6}),
            "scheduled_for": forms.DateTimeInput(
                attrs={"type": "datetime-local"}
            ),
        }

    def __init__(
        self,
        *args,
        studio=None,
        instructor=None,
        teacher_mode=False,
        template=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.use_required_attribute = False

        self.studio = studio
        self.teacher_mode = teacher_mode
        self.instructor = instructor
        self.instance.send_to_guardians = True

        if studio is not None:
            self.fields["template"].queryset = (
                EmailTemplate.objects
                .filter(studio=studio, is_active=True)
                .order_by("category", "name")
            )
            self.fields["signature"].queryset = (
                EmailSignature.objects
                .filter(studio=studio, is_active=True)
                .order_by("-is_default", "name")
            )

        self.fields["template"].required = False
        self.fields["scheduled_for"].required = False
        self.fields["recipient_selection"].required = True

        if self.instance and self.instance.pk:
            if self.instance.template_id:
                self.fields["message_source"].initial = "template"
            if self.instance.scheduled_for:
                self.fields["schedule_email"].initial = True

        if template is not None and not self.is_bound:
            self.fields["message_source"].initial = "template"
            self.fields["template"].initial = template
            self.fields["subject"].initial = template.subject
            self.fields["html_body"].initial = template.html_body
            self.fields["text_body"].initial = template.text_body
            self.fields["signature"].initial = template.signature
            self.fields["name"].initial = template.name

        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "encore-checkbox"
            elif not isinstance(field.widget, forms.HiddenInput):
                current = field.widget.attrs.get("class", "")
                field.widget.attrs["class"] = (
                    f"{current} encore-input".strip()
                )

    def clean(self):
        cleaned = super().clean()

        selection = cleaned.get("recipient_selection") or {}
        message_source = cleaned.get("message_source")
        template = cleaned.get("template")
        schedule_email = cleaned.get("schedule_email")
        scheduled_for = cleaned.get("scheduled_for")

        if not isinstance(selection, dict):
            self.add_error(
                "recipient_selection",
                "Choose at least one recipient group.",
            )
            return cleaned

        groups = selection.get("groups", {})
        all_selected = bool(selection.get("all"))
        has_selection = all_selected

        if isinstance(groups, dict):
            has_selection = has_selection or any(
                bool(values)
                for values in groups.values()
            )

        if not has_selection:
            self.add_error(
                "recipient_selection",
                "Choose at least one recipient.",
            )

        if message_source == "template" and template is None:
            self.add_error(
                "template",
                "Choose the template you want to use.",
            )

        if message_source == "new":
            cleaned["template"] = None

        if schedule_email and not scheduled_for:
            self.add_error(
                "scheduled_for",
                "Choose a date and time for the scheduled email.",
            )

        if not schedule_email:
            cleaned["scheduled_for"] = None

        return cleaned


class EmailAutomationRuleForm(forms.ModelForm):
    WEEKDAY_CHOICES = [
        (0, "Monday"),
        (1, "Tuesday"),
        (2, "Wednesday"),
        (3, "Thursday"),
        (4, "Friday"),
        (5, "Saturday"),
        (6, "Sunday"),
    ]

    weekday = forms.TypedChoiceField(
        choices=[("", "---------")] + WEEKDAY_CHOICES,
        coerce=int,
        empty_value=None,
        required=False,
    )

    class Meta:
        model = EmailAutomationRule
        fields = [
            "enabled",
            "name",
            "trigger_type",
            "audience_type",
            "timing_mode",
            "threshold_value",
            "threshold_amount",
            "delay_minutes",
            "offset_value",
            "offset_direction",
            "offset_unit",
            "weekday",
            "day_of_month",
            "month",
            "day_of_month_yearly",
            "time_of_day",
        ]

        labels = {
            "enabled": "Automatically send this template",
            "name": "Automation Name",
            "trigger_type": "Trigger",
            "audience_type": "Send To",
            "threshold_value": "Number / Threshold",
            "threshold_amount": "Amount ($)",
            "delay_minutes": "Delay (minutes)",
            "offset_value": "How Many",
            "offset_direction": "Before / After",
            "offset_unit": "Days / Weeks / Months",
            "day_of_month": "Day of Month",
            "month": "Month",
            "day_of_month_yearly": "Day",
            "time_of_day": "Time",
        }

        widgets = {
            "time_of_day": forms.TimeInput(attrs={"type": "time"}),
            "threshold_amount": forms.NumberInput(
                attrs={"min": "0", "step": "0.01"}
            ),
            "threshold_value": forms.NumberInput(attrs={"min": "1"}),
            "offset_value": forms.NumberInput(attrs={"min": "0"}),
            "delay_minutes": forms.NumberInput(attrs={"min": "0"}),
            "day_of_month": forms.NumberInput(
                attrs={"min": "1", "max": "31"}
            ),
            "month": forms.NumberInput(
                attrs={"min": "1", "max": "12"}
            ),
            "day_of_month_yearly": forms.NumberInput(
                attrs={"min": "1", "max": "31"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "encore-checkbox"
            else:
                field.widget.attrs["class"] = "encore-input"

        self.fields["trigger_type"].widget.attrs[
            "data-automation-trigger"
        ] = "true"
        self.fields["timing_mode"].widget.attrs[
            "data-automation-timing"
        ] = "true"


class AutomatedEmailSettingForm(forms.ModelForm):
    class Meta:
        model = AutomatedEmailSetting
        fields = [
            "enabled",
            "template",
            "sender_type",
            "send_to_guardians",
            "send_to_students",
            "delay_minutes",
        ]

        labels = {
            "delay_minutes": "Delay Before Sending (minutes)",
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

        if studio is not None:
            self.fields[
                "template"
            ].queryset = (
                EmailTemplate.objects
                .filter(
                    studio=studio,
                    is_active=True,
                )
                .order_by(
                    "category",
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
