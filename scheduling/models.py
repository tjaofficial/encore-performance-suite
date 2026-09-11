from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from classes.models import Class
from instructors.models import Instructor
from studios.models import Studio


class CalendarEvent(models.Model):
    class EventType(models.TextChoices):
        GENERAL = "general", "General"
        CLOSURE = "closure", "Studio Closure"
        PERFORMANCE = "performance", "Performance"
        REHEARSAL = "rehearsal", "Rehearsal"
        MEETING = "meeting", "Meeting"
        DEADLINE = "deadline", "Deadline"
        OTHER = "other", "Other"

    class Audience(models.TextChoices):
        STUDIO = "studio", "Entire Studio"
        ADMINS = "admins", "Administrators Only"
        TEACHERS = "teachers", "Teachers Only"
        CLASS_MEMBERS = "class_members", "Class Members"

    studio = models.ForeignKey(
        Studio,
        on_delete=models.CASCADE,
        related_name="calendar_events",
    )

    class Scope(models.TextChoices):
        MAIN = "main", "Main Event"
        PERSONAL = "personal", "Personal Event"

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    scope = models.CharField(
        max_length=20,
        choices=Scope.choices,
        default=Scope.MAIN,
    )

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="personal_calendar_events",
        null=True,
        blank=True,
        help_text="Required for Personal Events. Main Events are studio-owned.",
    )

    category = models.ForeignKey(
        "CalendarCategory",
        on_delete=models.SET_NULL,
        related_name="events",
        null=True,
        blank=True,
    )

    color = models.CharField(
        max_length=7,
        blank=True,
        help_text="Optional event color override. Category color is used otherwise.",
    )

    is_public = models.BooleanField(
        default=False,
        help_text="Allows this event to appear in public calendar widgets later.",
    )

    event_type = models.CharField(
        max_length=30,
        choices=EventType.choices,
        default=EventType.GENERAL,
    )

    audience = models.CharField(
        max_length=30,
        choices=Audience.choices,
        default=Audience.STUDIO,
    )

    class_instance = models.ForeignKey(
        Class,
        on_delete=models.CASCADE,
        related_name="calendar_events",
        null=True,
        blank=True,
        help_text="Required when audience is Class Members.",
    )

    instructor = models.ForeignKey(
        Instructor,
        on_delete=models.SET_NULL,
        related_name="calendar_events",
        null=True,
        blank=True,
        help_text="Optional instructor associated with this event.",
    )

    start_at = models.DateTimeField()
    end_at = models.DateTimeField()

    all_day = models.BooleanField(default=False)

    location = models.CharField(
        max_length=255,
        blank=True,
    )

    notes = models.TextField(blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="created_calendar_events",
        null=True,
        blank=True,
    )

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["start_at", "title"]

    def clean(self):
        super().clean()

        if self.start_at and self.end_at and self.end_at <= self.start_at:
            raise ValidationError(
                {"end_at": "Event end time must be after the start time."}
            )

        if self.audience == self.Audience.CLASS_MEMBERS and not self.class_instance:
            raise ValidationError(
                {
                    "class_instance": (
                        "Select a class when the audience is Class Members."
                    )
                }
            )

        if self.class_instance_id and self.class_instance.studio_id != self.studio_id:
            raise ValidationError(
                {"class_instance": "The selected class must belong to this studio."}
            )

        if self.instructor_id and self.instructor.studio_id != self.studio_id:
            raise ValidationError(
                {"instructor": "The selected instructor must belong to this studio."}
            )

        if self.scope == self.Scope.PERSONAL and not self.owner_id:
            raise ValidationError(
                {"owner": "Personal events require an owner."}
            )

        if self.scope == self.Scope.MAIN and self.owner_id:
            raise ValidationError(
                {"owner": "Main events are studio-wide and cannot have a personal owner."}
            )

        if self.category_id and self.category.studio_id != self.studio_id:
            raise ValidationError(
                {"category": "The selected category must belong to this studio."}
            )

        if self.category_id:
            if self.category.scope != self.scope:
                raise ValidationError(
                    {"category": "Category type must match the event type."}
                )
            if (
                self.scope == self.Scope.PERSONAL
                and self.category.owner_id != self.owner_id
            ):
                raise ValidationError(
                    {"category": "Personal event category must belong to the event owner."}
                )

    def __str__(self):
        return f"{self.title} - {self.start_at:%Y-%m-%d %H:%M}"


class CalendarCategory(models.Model):
    class Scope(models.TextChoices):
        MAIN = "main", "Main Event"
        PERSONAL = "personal", "Personal Event"

    studio = models.ForeignKey(
        Studio,
        on_delete=models.CASCADE,
        related_name="calendar_categories",
    )
    name = models.CharField(max_length=120)
    scope = models.CharField(
        max_length=20,
        choices=Scope.choices,
        default=Scope.MAIN,
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="personal_calendar_categories",
        null=True,
        blank=True,
    )
    color = models.CharField(
        max_length=7,
        default="#2E3CF1",
    )
    is_public = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["scope", "sort_order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["studio", "scope", "owner", "name"],
                name="unique_calendar_category_per_owner",
            )
        ]

    def clean(self):
        super().clean()
        if self.scope == self.Scope.PERSONAL and not self.owner_id:
            raise ValidationError(
                {"owner": "Personal calendar categories require an owner."}
            )
        if self.scope == self.Scope.MAIN and self.owner_id:
            raise ValidationError(
                {"owner": "Main event categories are studio-wide and cannot have an owner."}
            )

    def __str__(self):
        return self.name


class CalendarRecurrence(models.Model):
    class Frequency(models.TextChoices):
        DAILY = "daily", "Daily"
        WEEKLY = "weekly", "Weekly"
        MONTHLY = "monthly", "Monthly"
        YEARLY = "yearly", "Yearly"

    class EndType(models.TextChoices):
        NEVER = "never", "Never"
        ON_DATE = "on_date", "On Date"
        AFTER_COUNT = "after_count", "After Number of Occurrences"

    event = models.OneToOneField(
        CalendarEvent,
        on_delete=models.CASCADE,
        related_name="recurrence",
    )
    frequency = models.CharField(
        max_length=20,
        choices=Frequency.choices,
        default=Frequency.WEEKLY,
    )
    interval = models.PositiveIntegerField(default=1)
    weekdays = models.JSONField(default=list, blank=True)
    end_type = models.CharField(
        max_length=20,
        choices=EndType.choices,
        default=EndType.NEVER,
    )
    end_date = models.DateField(null=True, blank=True)
    occurrence_count = models.PositiveIntegerField(null=True, blank=True)

    def clean(self):
        super().clean()
        if self.interval < 1:
            raise ValidationError({"interval": "Repeat interval must be at least 1."})
        if self.end_type == self.EndType.ON_DATE and not self.end_date:
            raise ValidationError({"end_date": "Choose an end date."})
        if self.end_type == self.EndType.AFTER_COUNT and not self.occurrence_count:
            raise ValidationError(
                {"occurrence_count": "Enter the number of occurrences."}
            )

    def __str__(self):
        return f"{self.event.title} recurrence"


class CalendarPreference(models.Model):
    class DefaultView(models.TextChoices):
        MONTH = "dayGridMonth", "Month"
        WEEK = "timeGridWeek", "Week"
        DAY = "timeGridDay", "Day"
        AGENDA = "listWeek", "Agenda"

    class WeekStart(models.IntegerChoices):
        SUNDAY = 0, "Sunday"
        MONDAY = 1, "Monday"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="calendar_preferences",
    )
    studio = models.ForeignKey(
        Studio,
        on_delete=models.CASCADE,
        related_name="calendar_preferences",
    )
    default_view = models.CharField(
        max_length=30,
        choices=DefaultView.choices,
        default=DefaultView.MONTH,
    )
    week_starts_on = models.PositiveSmallIntegerField(
        choices=WeekStart.choices,
        default=WeekStart.SUNDAY,
    )
    show_weekends = models.BooleanField(default=True)
    show_completed_tasks = models.BooleanField(default=False)
    dim_past_events = models.BooleanField(default=True)
    source_visibility = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "studio"],
                name="unique_calendar_preference_per_user_studio",
            )
        ]

    def __str__(self):
        return f"{self.user} - {self.studio} Calendar"


class CalendarEventException(models.Model):
    """
    Reserved for single-occurrence edits/cancellations of recurring calendar events.
    Calendar V1 stores the architecture now; occurrence editing can be layered on later.
    """
    event = models.ForeignKey(
        CalendarEvent,
        on_delete=models.CASCADE,
        related_name="exceptions",
    )
    original_start_at = models.DateTimeField()
    replacement_start_at = models.DateTimeField(null=True, blank=True)
    replacement_end_at = models.DateTimeField(null=True, blank=True)
    is_cancelled = models.BooleanField(default=False)
    title_override = models.CharField(max_length=200, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["original_start_at"]

    def __str__(self):
        return f"{self.event.title} - {self.original_start_at}"


class TeacherTimeOffRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PARTIAL = "partial", "Partially Approved"
        APPROVED = "approved", "Approved"
        DENIED = "denied", "Denied"

    studio = models.ForeignKey(
        Studio,
        on_delete=models.CASCADE,
        related_name="teacher_time_off_requests",
    )

    instructor = models.ForeignKey(
        Instructor,
        on_delete=models.CASCADE,
        related_name="time_off_requests",
    )

    reason = models.CharField(
        max_length=255,
    )

    notes = models.TextField(
        blank=True,
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="created_teacher_time_off_requests",
        null=True,
        blank=True,
    )

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="reviewed_teacher_time_off_requests",
        null=True,
        blank=True,
    )

    reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    admin_task = models.ForeignKey(
        "tasks.Task",
        on_delete=models.SET_NULL,
        related_name="teacher_time_off_requests",
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = [
            "-created_at",
        ]

    def clean(self):
        super().clean()

        if (
            self.instructor_id
            and self.instructor.studio_id
            != self.studio_id
        ):
            raise ValidationError(
                {
                    "instructor": (
                        "Instructor and time off request "
                        "must belong to the same studio."
                    )
                }
            )

    def refresh_status(self):
        date_statuses = list(
            self.dates.values_list(
                "status",
                flat=True,
            )
        )

        if not date_statuses:
            self.status = self.Status.PENDING

        elif all(
            status == TeacherTimeOffDate.Status.APPROVED
            for status in date_statuses
        ):
            self.status = self.Status.APPROVED

        elif all(
            status == TeacherTimeOffDate.Status.DENIED
            for status in date_statuses
        ):
            self.status = self.Status.DENIED

        elif any(
            status == TeacherTimeOffDate.Status.APPROVED
            for status in date_statuses
        ):
            self.status = self.Status.PARTIAL

        else:
            self.status = self.Status.PENDING

        self.save(
            update_fields=[
                "status",
                "updated_at",
            ]
        )

    def __str__(self):
        return (
            f"{self.instructor.full_name} - "
            f"{self.get_status_display()}"
        )


class TeacherTimeOffDate(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        COVERAGE_REQUIRED = "coverage_required", "Coverage Required"
        APPROVED = "approved", "Approved"
        DENIED = "denied", "Denied"

    request = models.ForeignKey(
        TeacherTimeOffRequest,
        on_delete=models.CASCADE,
        related_name="dates",
    )

    date = models.DateField()

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )

    decision_note = models.CharField(
        max_length=255,
        blank=True,
    )

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="reviewed_teacher_time_off_dates",
        null=True,
        blank=True,
    )

    reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:
        ordering = [
            "date",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "request",
                    "date",
                ],
                name="unique_teacher_time_off_request_date",
            )
        ]

    def __str__(self):
        return (
            f"{self.request.instructor.full_name} - "
            f"{self.date}"
        )


class ClassOccurrenceOverride(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        CANCELLED = "cancelled", "Cancelled"

    studio = models.ForeignKey(
        Studio,
        on_delete=models.CASCADE,
        related_name="class_occurrence_overrides",
    )

    class_instance = models.ForeignKey(
        Class,
        on_delete=models.CASCADE,
        related_name="occurrence_overrides",
    )

    meeting = models.ForeignKey(
        "classes.ClassMeeting",
        on_delete=models.CASCADE,
        related_name="occurrence_overrides",
    )

    occurrence_date = models.DateField()

    absent_instructor = models.ForeignKey(
        Instructor,
        on_delete=models.PROTECT,
        related_name="absence_occurrence_overrides",
    )

    substitute_instructor = models.ForeignKey(
        Instructor,
        on_delete=models.PROTECT,
        related_name="substitute_occurrence_overrides",
    )

    time_off_date = models.ForeignKey(
        TeacherTimeOffDate,
        on_delete=models.CASCADE,
        related_name="class_occurrence_overrides",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="created_class_occurrence_overrides",
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = [
            "occurrence_date",
            "meeting__start_time",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "class_instance",
                    "meeting",
                    "occurrence_date",
                    "absent_instructor",
                ],
                name="unique_class_occurrence_absent_instructor",
            )
        ]

    def clean(self):
        super().clean()

        if (
            self.class_instance_id
            and self.class_instance.studio_id
            != self.studio_id
        ):
            raise ValidationError(
                {
                    "class_instance": (
                        "Class and occurrence override "
                        "must belong to the same studio."
                    )
                }
            )

        if (
            self.meeting_id
            and self.meeting.class_instance_id
            != self.class_instance_id
        ):
            raise ValidationError(
                {
                    "meeting": (
                        "Meeting must belong to the selected class."
                    )
                }
            )

        if (
            self.absent_instructor_id
            and self.absent_instructor.studio_id
            != self.studio_id
        ):
            raise ValidationError(
                {
                    "absent_instructor": (
                        "Absent instructor must belong "
                        "to the same studio."
                    )
                }
            )

        if (
            self.substitute_instructor_id
            and self.substitute_instructor.studio_id
            != self.studio_id
        ):
            raise ValidationError(
                {
                    "substitute_instructor": (
                        "Substitute instructor must belong "
                        "to the same studio."
                    )
                }
            )

        if (
            self.absent_instructor_id
            and self.substitute_instructor_id
            and self.absent_instructor_id
            == self.substitute_instructor_id
        ):
            raise ValidationError(
                {
                    "substitute_instructor": (
                        "Substitute must be a different instructor."
                    )
                }
            )

    def __str__(self):
        return (
            f"{self.class_instance.name} - "
            f"{self.occurrence_date} - "
            f"{self.substitute_instructor.full_name}"
        )
