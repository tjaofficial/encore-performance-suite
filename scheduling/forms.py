from datetime import date

from django import forms
from django.db.models import Q
from django.utils import timezone

from .models import (
    CalendarCategory,
    CalendarEvent,
    CalendarPreference,
    CalendarRecurrence,
)


class CalendarEventForm(forms.ModelForm):
    recurrence_preset = forms.ChoiceField(
        required=False,
        choices=[
            ("none", "Does not repeat"),
            ("daily", "Daily"),
            ("weekdays", "Every weekday"),
            ("weekly", "Weekly"),
            ("monthly", "Monthly"),
            ("yearly", "Annually"),
            ("custom", "Custom..."),
        ],
        initial="none",
        label="Repeats",
    )

    custom_frequency = forms.ChoiceField(
        required=False,
        choices=CalendarRecurrence.Frequency.choices,
        initial=CalendarRecurrence.Frequency.WEEKLY,
    )
    custom_interval = forms.IntegerField(
        required=False,
        min_value=1,
        initial=1,
    )
    custom_weekdays = forms.MultipleChoiceField(
        required=False,
        choices=[
            ("0", "Mon"),
            ("1", "Tue"),
            ("2", "Wed"),
            ("3", "Thu"),
            ("4", "Fri"),
            ("5", "Sat"),
            ("6", "Sun"),
        ],
    )
    custom_end_type = forms.ChoiceField(
        required=False,
        choices=CalendarRecurrence.EndType.choices,
        initial=CalendarRecurrence.EndType.NEVER,
    )
    custom_end_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    custom_occurrence_count = forms.IntegerField(
        required=False,
        min_value=1,
    )

    class Meta:
        model = CalendarEvent
        fields = [
            "scope",
            "title",
            "description",
            "event_type",
            "category",
            "start_at",
            "end_at",
            "all_day",
            "location",
            "notes",
            "is_public",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "notes": forms.Textarea(attrs={"rows": 3}),
            "start_at": forms.DateTimeInput(
                attrs={"type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "end_at": forms.DateTimeInput(
                attrs={"type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
        }

    def __init__(
        self,
        *args,
        studio=None,
        user=None,
        role=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self.studio = studio
        self.user = user
        self.role = role

        self.fields["start_at"].input_formats = [
            "%Y-%m-%dT%H:%M",
        ]
        self.fields["end_at"].input_formats = [
            "%Y-%m-%dT%H:%M",
        ]

        allowed_scopes = [
            (
                CalendarEvent.Scope.PERSONAL,
                "Personal Event",
            ),
        ]

        if role == "administrator":
            allowed_scopes.insert(
                0,
                (
                    CalendarEvent.Scope.MAIN,
                    "Main Event",
                ),
            )

        self.fields["scope"].choices = allowed_scopes

        categories = CalendarCategory.objects.none()

        if studio and user:
            categories = CalendarCategory.objects.filter(
                studio=studio,
                is_active=True,
            ).filter(
                Q(
                    scope=CalendarCategory.Scope.MAIN,
                    owner__isnull=True,
                )
                | Q(
                    scope=CalendarCategory.Scope.PERSONAL,
                    owner=user,
                )
            )

        self.fields["category"].queryset = categories.order_by(
            "scope",
            "sort_order",
            "name",
        )
        self.fields["category"].required = False
        self.fields["category"].empty_label = "No category"

        self.fields["is_public"].label = "Show on Public Calendar Widget"
        self.fields["all_day"].label = "All Day"

        if role != "administrator":
            self.fields["is_public"].widget = forms.HiddenInput()
            self.fields["event_type"].widget = forms.HiddenInput()

        recurrence = getattr(
            self.instance,
            "recurrence",
            None,
        )

        if recurrence:
            self.fields["recurrence_preset"].initial = "custom"
            self.fields["custom_frequency"].initial = recurrence.frequency
            self.fields["custom_interval"].initial = recurrence.interval
            self.fields["custom_weekdays"].initial = [
                str(day)
                for day in recurrence.weekdays
            ]
            self.fields["custom_end_type"].initial = recurrence.end_type
            self.fields["custom_end_date"].initial = recurrence.end_date
            self.fields["custom_occurrence_count"].initial = recurrence.occurrence_count

        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "calendar-checkbox"
            else:
                field.widget.attrs["class"] = "calendar-input"

    def clean(self):
        cleaned = super().clean()

        scope = cleaned.get("scope")

        if self.role != "administrator":
            cleaned["scope"] = CalendarEvent.Scope.PERSONAL
            scope = CalendarEvent.Scope.PERSONAL

        # CalendarEvent.clean() runs during ModelForm validation, before
        # CalendarEventForm.save(). Set the non-form ownership fields now so
        # personal events validate as the event they will actually become.
        self.instance.studio = self.studio

        if scope == CalendarEvent.Scope.PERSONAL:
            self.instance.owner = self.user
            self.instance.audience = (
                CalendarEvent.Audience.TEACHERS
                if self.role == "teacher"
                else CalendarEvent.Audience.ADMINS
            )
            self.instance.is_public = False
        else:
            self.instance.owner = None
            self.instance.audience = CalendarEvent.Audience.STUDIO

        if scope == CalendarEvent.Scope.MAIN and self.role != "administrator":
            self.add_error(
                "scope",
                "Only administrators can create Main Events.",
            )

        if cleaned.get("all_day"):
            start_at = cleaned.get("start_at")
            end_at = cleaned.get("end_at")

            if start_at and end_at:
                cleaned["start_at"] = start_at.replace(
                    hour=0,
                    minute=0,
                    second=0,
                    microsecond=0,
                )
                cleaned["end_at"] = end_at.replace(
                    hour=23,
                    minute=59,
                    second=59,
                    microsecond=0,
                )

        if cleaned.get("recurrence_preset") == "custom":
            end_type = cleaned.get(
                "custom_end_type",
            )

            if (
                end_type
                == CalendarRecurrence.EndType.ON_DATE
                and not cleaned.get("custom_end_date")
            ):
                self.add_error(
                    "custom_end_date",
                    "Choose the date when this recurrence should end.",
                )

            if (
                end_type
                == CalendarRecurrence.EndType.AFTER_COUNT
                and not cleaned.get("custom_occurrence_count")
            ):
                self.add_error(
                    "custom_occurrence_count",
                    "Enter how many occurrences should be created.",
                )

        return cleaned

    def save(self, commit=True):
        event = super().save(commit=False)

        event.studio = self.studio

        if event.scope == CalendarEvent.Scope.PERSONAL:
            event.owner = self.user
            event.audience = CalendarEvent.Audience.ADMINS
            if self.role == "teacher":
                event.audience = CalendarEvent.Audience.TEACHERS
            event.is_public = False
        else:
            event.owner = None
            event.audience = CalendarEvent.Audience.STUDIO

        event.created_by = event.created_by or self.user

        if commit:
            event.full_clean()
            event.save()

            self._save_recurrence(event)

        return event

    def _save_recurrence(self, event):
        preset = self.cleaned_data.get(
            "recurrence_preset",
            "none",
        )

        if preset == "none":
            CalendarRecurrence.objects.filter(
                event=event,
            ).delete()
            return

        frequency = CalendarRecurrence.Frequency.WEEKLY
        interval = 1
        weekdays = []
        end_type = CalendarRecurrence.EndType.NEVER
        end_date = None
        occurrence_count = None

        if preset == "daily":
            frequency = CalendarRecurrence.Frequency.DAILY

        elif preset == "weekdays":
            frequency = CalendarRecurrence.Frequency.WEEKLY
            weekdays = [0, 1, 2, 3, 4]

        elif preset == "weekly":
            frequency = CalendarRecurrence.Frequency.WEEKLY
            weekdays = [event.start_at.weekday()]

        elif preset == "monthly":
            frequency = CalendarRecurrence.Frequency.MONTHLY

        elif preset == "yearly":
            frequency = CalendarRecurrence.Frequency.YEARLY

        elif preset == "custom":
            frequency = self.cleaned_data.get(
                "custom_frequency",
            ) or CalendarRecurrence.Frequency.WEEKLY

            interval = self.cleaned_data.get(
                "custom_interval",
            ) or 1

            weekdays = [
                int(value)
                for value in self.cleaned_data.get(
                    "custom_weekdays",
                    [],
                )
            ]

            end_type = self.cleaned_data.get(
                "custom_end_type",
            ) or CalendarRecurrence.EndType.NEVER

            end_date = self.cleaned_data.get(
                "custom_end_date",
            )

            occurrence_count = self.cleaned_data.get(
                "custom_occurrence_count",
            )

        recurrence, _ = CalendarRecurrence.objects.update_or_create(
            event=event,
            defaults={
                "frequency": frequency,
                "interval": interval,
                "weekdays": weekdays,
                "end_type": end_type,
                "end_date": end_date,
                "occurrence_count": occurrence_count,
            },
        )

        recurrence.full_clean()


class CalendarCategoryForm(forms.ModelForm):
    class Meta:
        model = CalendarCategory
        fields = [
            "name",
            "color",
        ]
        widgets = {
            "color": forms.TextInput(
                attrs={"type": "color"},
            )
        }

    def __init__(
        self,
        *args,
        studio=None,
        user=None,
        scope=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.studio = studio
        self.user = user
        self.scope = scope

        for field in self.fields.values():
            field.widget.attrs["class"] = "calendar-input"

    def save(self, commit=True):
        category = super().save(commit=False)
        category.studio = self.studio
        category.scope = self.scope

        if self.scope == CalendarCategory.Scope.PERSONAL:
            category.owner = self.user
            category.is_public = False
        else:
            category.owner = None

        if commit:
            category.full_clean()
            category.save()

        return category


class CalendarPreferenceForm(forms.ModelForm):
    class Meta:
        model = CalendarPreference
        fields = [
            "default_view",
            "week_starts_on",
            "show_weekends",
            "show_completed_tasks",
            "dim_past_events",
        ]


from instructors.models import Instructor
from .models import (
    TeacherTimeOffRequest,
    TeacherTimeOffDate,
    ClassOccurrenceOverride,
)


class TeacherTimeOffRequestForm(forms.ModelForm):
    dates = forms.CharField(
        label="Dates",
        help_text=(
            "Choose one or more dates."
        ),
        widget=forms.HiddenInput(),
    )

    class Meta:
        model = TeacherTimeOffRequest
        fields = [
            "reason",
            "notes",
        ]

        widgets = {
            "reason": forms.TextInput(
                attrs={
                    "placeholder": (
                        "Vacation, appointment, personal day..."
                    ),
                }
            ),
            "notes": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": (
                        "Optional details for the administrator."
                    ),
                }
            ),
        }

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
            ] = "calendar-input"

    def clean_dates(self):
        raw = (
            self.cleaned_data.get(
                "dates",
                "",
            )
            or ""
        )

        values = []

        for item in raw.split(","):
            item = item.strip()

            if not item:
                continue

            try:
                parsed = date.fromisoformat(
                    item
                )
            except ValueError:
                raise forms.ValidationError(
                    "One or more selected dates are invalid."
                )

            if parsed not in values:
                values.append(
                    parsed
                )

        if not values:
            raise forms.ValidationError(
                "Choose at least one date."
            )

        return sorted(
            values
        )


class TimeOffDecisionForm(forms.Form):
    decision_note = forms.CharField(
        required=False,
        label="Admin Note",
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": (
                    "Optional note for the teacher."
                ),
            }
        ),
    )

    def __init__(
        self,
        *args,
        time_off_request=None,
        **kwargs,
    ):
        super().__init__(
            *args,
            **kwargs,
        )

        self.time_off_request = (
            time_off_request
        )

        if time_off_request:
            for date_record in (
                time_off_request.dates.all()
            ):
                self.fields[
                    f"date_{date_record.pk}"
                ] = forms.ChoiceField(
                    label=date_record.date.strftime(
                        "%A, %B %-d, %Y"
                    ),
                    choices=[
                        (
                            TeacherTimeOffDate.Status.PENDING,
                            "Pending",
                        ),
                        (
                            TeacherTimeOffDate.Status.APPROVED,
                            "Approve",
                        ),
                        (
                            TeacherTimeOffDate.Status.DENIED,
                            "Deny",
                        ),
                    ],
                    initial=(
                        TeacherTimeOffDate.Status.APPROVED
                        if date_record.status
                        == TeacherTimeOffDate.Status.COVERAGE_REQUIRED
                        else date_record.status
                    ),
                )

        for field in self.fields.values():
            field.widget.attrs[
                "class"
            ] = "calendar-input"


class SubstituteCoverageForm(forms.Form):
    def __init__(
        self,
        *args,
        occurrence_rows=None,
        studio=None,
        **kwargs,
    ):
        super().__init__(
            *args,
            **kwargs,
        )

        self.occurrence_rows = list(
            occurrence_rows
            or []
        )

        for row in self.occurrence_rows:
            date_record = row[
                "time_off_date"
            ]
            meeting = row[
                "meeting"
            ]
            absent = row[
                "absent_instructor"
            ]

            field_name = (
                f"substitute_"
                f"{date_record.pk}_"
                f"{meeting.pk}"
            )

            existing = row.get(
                "existing_override"
            )

            availability = row.get(
                "substitute_availability",
                {},
            )

            available_ids = (
                availability.get(
                    "available_ids",
                    [],
                )
            )

            queryset = (
                Instructor.objects
                .filter(
                    studio=studio,
                    is_active=True,
                    pk__in=available_ids,
                )
                .exclude(
                    pk=absent.pk,
                )
                .order_by(
                    "last_name",
                    "first_name",
                )
            )

            self.fields[
                field_name
            ] = forms.ModelChoiceField(
                queryset=queryset,
                required=True,
                label=(
                    f"{row['class_instance'].name} · "
                    f"{meeting.start_time.strftime('%-I:%M %p')}"
                ),
                initial=(
                    existing.substitute_instructor_id
                    if existing
                    else None
                ),
                empty_label="Select substitute teacher",
            )

            self.fields[
                field_name
            ].widget.attrs[
                "class"
            ] = "calendar-input"
