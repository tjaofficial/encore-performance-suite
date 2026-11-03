from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from classes.models import Class
from instructors.models import Instructor
from studios.models import Studio


class Announcement(models.Model):
    class Audience(models.TextChoices):
        STUDIO = "studio", "Entire Studio"
        CLASS = "class", "Specific Class(es)"
        STAFF = "staff", "All Staff"
        TEACHERS = "teachers", "Teachers"
        FAMILIES = "families", "Families"
        STUDENTS = "students", "Students"

    class Priority(models.TextChoices):
        NORMAL = "normal", "Normal"
        IMPORTANT = "important", "Important"
        URGENT = "urgent", "Urgent"

    studio = models.ForeignKey(
        Studio,
        on_delete=models.CASCADE,
        related_name="announcements",
    )

    title = models.CharField(
        max_length=200,
    )

    message = models.TextField()

    audience = models.CharField(
        max_length=20,
        choices=Audience.choices,
        default=Audience.STUDIO,
    )

    classes = models.ManyToManyField(
        Class,
        related_name="announcements",
        blank=True,
    )

    priority = models.CharField(
        max_length=20,
        choices=Priority.choices,
        default=Priority.NORMAL,
    )

    is_pinned = models.BooleanField(
        default=False,
    )

    is_published = models.BooleanField(
        default=True,
    )

    publish_at = models.DateTimeField(
        default=timezone.now,
    )

    expires_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="created_announcements",
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
            "-is_pinned",
            "-publish_at",
            "-created_at",
        ]

    def clean(self):
        super().clean()

        if (
            self.expires_at
            and self.expires_at <= self.publish_at
        ):
            raise ValidationError(
                {
                    "expires_at": (
                        "Expiration must be after the publish date."
                    )
                }
            )

    @property
    def is_live(self):
        now = timezone.now()

        if not self.is_published:
            return False

        if self.publish_at > now:
            return False

        if self.expires_at and self.expires_at <= now:
            return False

        return True

    def __str__(self):
        return self.title


class AnnouncementRead(models.Model):
    announcement = models.ForeignKey(
        Announcement,
        on_delete=models.CASCADE,
        related_name="read_receipts",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="announcement_reads",
    )

    read_at = models.DateTimeField(
        default=timezone.now,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "announcement",
                    "user",
                ],
                name="unique_announcement_read_per_user",
            )
        ]

    def __str__(self):
        return (
            f"{self.user} read "
            f"{self.announcement}"
        )



class EmailSignature(models.Model):
    studio = models.ForeignKey(
        Studio,
        on_delete=models.CASCADE,
        related_name="email_signatures",
    )

    name = models.CharField(
        max_length=120,
    )

    body = models.TextField()

    is_default = models.BooleanField(
        default=False,
    )

    is_active = models.BooleanField(
        default=True,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="created_email_signatures",
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
            "-is_default",
            "name",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "studio",
                    "name",
                ],
                name="unique_email_signature_name_per_studio",
            )
        ]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        if self.is_default:
            EmailSignature.objects.filter(
                studio=self.studio,
            ).exclude(
                pk=self.pk,
            ).update(
                is_default=False,
            )

    def __str__(self):
        return self.name


class EmailTemplate(models.Model):
    class Category(models.TextChoices):
        GENERAL = "general", "General"
        BIRTHDAY = "birthday", "Birthday"
        REGISTRATION = "registration", "Registration"
        ENROLLMENT = "enrollment", "Enrollment"
        PAYMENT = "payment", "Payment"
        PERFORMANCE = "performance", "Performance"
        COSTUME = "costume", "Costume"
        ATTENDANCE = "attendance", "Attendance"
        EVENT = "event", "Event"
        TASK = "task", "Task"
        ANNOUNCEMENT = "announcement", "Studio Announcement"
        CUSTOM = "custom", "Custom"

    studio = models.ForeignKey(
        Studio,
        on_delete=models.CASCADE,
        related_name="email_templates",
    )

    name = models.CharField(
        max_length=160,
    )

    category = models.CharField(
        max_length=30,
        choices=Category.choices,
        default=Category.GENERAL,
    )

    subject = models.CharField(
        max_length=255,
    )

    html_body = models.TextField()

    text_body = models.TextField(
        blank=True,
    )

    signature = models.ForeignKey(
        EmailSignature,
        on_delete=models.SET_NULL,
        related_name="templates",
        null=True,
        blank=True,
    )

    is_system_default = models.BooleanField(
        default=False,
    )

    is_active = models.BooleanField(
        default=True,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="created_email_templates",
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
            "category",
            "name",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "studio",
                    "name",
                ],
                name="unique_email_template_name_per_studio",
            )
        ]

    def __str__(self):
        return self.name


class EmailCampaign(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SCHEDULED = "scheduled", "Scheduled"
        SENDING = "sending", "Sending"
        SENT = "sent", "Sent"
        PARTIAL_FAILED = "partial_failed", "Partially Failed"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    class RecipientMode(models.TextChoices):
        MIXED = "mixed", "Selected Audience"
        FAMILIES_STUDENTS = (
            "families_students",
            "Group of Students / Families",
        )
        INSTRUCTOR_CLASSES = (
            "instructor_classes",
            "Students in Instructor Classes",
        )
        INSTRUCTORS = (
            "instructors",
            "Group of Instructors",
        )
        CLASSES = (
            "classes",
            "Group of Classes",
        )

    class SenderType(models.TextChoices):
        NO_REPLY = (
            "no_reply",
            "Encore Notifications (no-reply)",
        )
        INFO = (
            "info",
            "Encore Information (info)",
        )

    studio = models.ForeignKey(
        Studio,
        on_delete=models.CASCADE,
        related_name="email_campaigns",
    )

    name = models.CharField(
        max_length=180,
    )

    subject = models.CharField(
        max_length=255,
    )

    html_body = models.TextField()

    text_body = models.TextField(
        blank=True,
    )

    template = models.ForeignKey(
        EmailTemplate,
        on_delete=models.SET_NULL,
        related_name="campaigns",
        null=True,
        blank=True,
    )

    signature = models.ForeignKey(
        EmailSignature,
        on_delete=models.SET_NULL,
        related_name="campaigns",
        null=True,
        blank=True,
    )

    sender_type = models.CharField(
        max_length=20,
        choices=SenderType.choices,
        default=SenderType.INFO,
    )

    recipient_mode = models.CharField(
        max_length=40,
        choices=RecipientMode.choices,
        default=RecipientMode.FAMILIES_STUDENTS,
    )

    recipient_selection = models.JSONField(
        default=dict,
        blank=True,
    )

    selected_classes = models.ManyToManyField(
        Class,
        related_name="email_campaigns",
        blank=True,
    )

    selected_instructors = models.ManyToManyField(
        Instructor,
        related_name="email_campaigns",
        blank=True,
    )

    send_to_guardians = models.BooleanField(
        default=True,
    )

    send_to_students = models.BooleanField(
        default=False,
    )

    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.DRAFT,
    )

    scheduled_for = models.DateTimeField(
        null=True,
        blank=True,
    )

    sent_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    total_recipients = models.PositiveIntegerField(
        default=0,
    )

    sent_count = models.PositiveIntegerField(
        default=0,
    )

    delivered_count = models.PositiveIntegerField(
        default=0,
    )

    opened_count = models.PositiveIntegerField(
        default=0,
    )

    clicked_count = models.PositiveIntegerField(
        default=0,
    )

    failed_count = models.PositiveIntegerField(
        default=0,
    )

    bounced_count = models.PositiveIntegerField(
        default=0,
    )

    complaint_count = models.PositiveIntegerField(
        default=0,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="created_email_campaigns",
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

    def __str__(self):
        return self.name


class EmailCampaignRecipient(models.Model):
    class RecipientType(models.TextChoices):
        GUARDIAN = "guardian", "Guardian / Family"
        STUDENT = "student", "Student"
        INSTRUCTOR = "instructor", "Instructor"
        ADMIN = "admin", "Administrator"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        SENT = "sent", "Sent"
        DELIVERED = "delivered", "Delivered"
        OPENED = "opened", "Opened"
        CLICKED = "clicked", "Clicked"
        DELAYED = "delayed", "Delayed"
        BOUNCED = "bounced", "Bounced"
        COMPLAINT = "complaint", "Complaint"
        FAILED = "failed", "Failed"
        SUPPRESSED = "suppressed", "Suppressed"

    campaign = models.ForeignKey(
        EmailCampaign,
        on_delete=models.CASCADE,
        related_name="recipients",
    )

    email = models.EmailField()

    display_name = models.CharField(
        max_length=255,
        blank=True,
    )

    recipient_type = models.CharField(
        max_length=20,
        choices=RecipientType.choices,
        default=RecipientType.OTHER,
    )

    source_key = models.CharField(
        max_length=120,
        blank=True,
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.QUEUED,
    )

    ses_message_id = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
    )

    error_message = models.TextField(
        blank=True,
    )

    sent_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    delivered_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    opened_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    clicked_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    bounced_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    complained_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = [
            "email",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "campaign",
                    "email",
                ],
                name="unique_email_per_campaign",
            )
        ]

    def __str__(self):
        return f"{self.campaign.name} - {self.email}"


class EmailEvent(models.Model):
    class EventType(models.TextChoices):
        SEND = "send", "Send"
        DELIVERY = "delivery", "Delivery"
        OPEN = "open", "Open"
        CLICK = "click", "Click"
        BOUNCE = "bounce", "Bounce"
        COMPLAINT = "complaint", "Complaint"
        REJECT = "reject", "Reject"
        RENDERING_FAILURE = (
            "rendering_failure",
            "Rendering Failure",
        )
        DELIVERY_DELAY = (
            "delivery_delay",
            "Delivery Delay",
        )
        SUBSCRIPTION = (
            "subscription",
            "Subscription Change",
        )

    recipient = models.ForeignKey(
        EmailCampaignRecipient,
        on_delete=models.CASCADE,
        related_name="events",
    )

    event_type = models.CharField(
        max_length=30,
        choices=EventType.choices,
    )

    provider_event_id = models.CharField(
        max_length=255,
        blank=True,
    )

    occurred_at = models.DateTimeField(
        default=timezone.now,
    )

    payload = models.JSONField(
        default=dict,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = [
            "-occurred_at",
        ]

    def __str__(self):
        return f"{self.recipient.email} - {self.event_type}"


class EmailSuppression(models.Model):
    class Reason(models.TextChoices):
        HARD_BOUNCE = "hard_bounce", "Hard Bounce"
        COMPLAINT = "complaint", "Complaint"
        UNSUBSCRIBED = "unsubscribed", "Unsubscribed"
        MANUAL = "manual", "Manual"
        INVALID = "invalid", "Invalid Address"

    studio = models.ForeignKey(
        Studio,
        on_delete=models.CASCADE,
        related_name="email_suppressions",
    )

    email = models.EmailField()

    reason = models.CharField(
        max_length=30,
        choices=Reason.choices,
    )

    is_active = models.BooleanField(
        default=True,
    )

    notes = models.TextField(
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
            "email",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "studio",
                    "email",
                ],
                name="unique_email_suppression_per_studio",
            )
        ]

    def __str__(self):
        return self.email


class AutomatedEmailSetting(models.Model):
    class Trigger(models.TextChoices):
        REGISTRATION_STARTED = (
            "registration_started",
            "Registration Started",
        )
        ENROLLMENT_CONFIRMATION = (
            "enrollment_confirmation",
            "Enrollment Confirmation",
        )
        REGISTRATION_COMPLETE = (
            "registration_complete",
            "Registration Complete",
        )
        PAYMENT_CONFIRMATION = (
            "payment_confirmation",
            "Payment Confirmation",
        )
        TASK_ASSIGNED = (
            "task_assigned",
            "Task Assigned",
        )
        EVENT_ANNOUNCEMENT = (
            "event_announcement",
            "Event Announcement",
        )
        BIRTHDAY = (
            "birthday",
            "Birthday",
        )
        COSTUME_INFORMATION = (
            "costume_information",
            "Costume Information",
        )

    class SenderType(models.TextChoices):
        NO_REPLY = (
            "no_reply",
            "Encore Notifications (no-reply)",
        )
        INFO = (
            "info",
            "Encore Information (info)",
        )

    studio = models.ForeignKey(
        Studio,
        on_delete=models.CASCADE,
        related_name="automated_email_settings",
    )

    trigger = models.CharField(
        max_length=40,
        choices=Trigger.choices,
    )

    enabled = models.BooleanField(
        default=True,
    )

    template = models.ForeignKey(
        EmailTemplate,
        on_delete=models.SET_NULL,
        related_name="automation_settings",
        null=True,
        blank=True,
    )

    sender_type = models.CharField(
        max_length=20,
        choices=SenderType.choices,
        default=SenderType.NO_REPLY,
    )

    send_to_guardians = models.BooleanField(
        default=True,
    )

    send_to_students = models.BooleanField(
        default=False,
    )

    delay_minutes = models.PositiveIntegerField(
        default=0,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = [
            "trigger",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "studio",
                    "trigger",
                ],
                name="unique_automated_email_trigger_per_studio",
            )
        ]

    def __str__(self):
        return self.get_trigger_display()


class EmailAutomationRule(models.Model):
    class TriggerType(models.TextChoices):
        WEEKLY = "weekly", "Day / Time Each Week"
        MONTHLY = "monthly", "Day / Time Each Month"
        YEARLY = "yearly", "Date / Time Each Year"
        STUDENT_ADDED = "student_added", "Student Added"
        STUDENT_ENROLLED = "student_enrolled", "Student Enrolled"
        STUDENT_DROPPED = "student_dropped", "Student Dropped"
        CONSECUTIVE_ABSENCES = "consecutive_absences", "Consecutive Absences"
        TOTAL_ABSENCES = "total_absences", "Total Absences"
        BIRTHDAY = "birthday", "Student Birthday"
        CLASS_CREATED = "class_created", "Class Created"
        REGISTRATION_OPENS = "registration_opens", "Registration Opens"
        REGISTRATION_CLOSES = "registration_closes", "Registration Closes"
        CLASS_STARTS = "class_starts", "Class Starts"
        CLASS_CANCELLED = "class_cancelled", "Class Cancelled"
        CLASS_CAPACITY = "class_capacity", "Class Reaches Capacity"
        WAITLIST_THRESHOLD = "waitlist_threshold", "Waitlist Reaches a Number"
        INSTRUCTOR_ADDED = "instructor_added", "Instructor Added"
        INSTRUCTOR_ASSIGNED = "instructor_assigned", "Instructor Assigned to Class"
        SUBSTITUTE_ASSIGNED = "substitute_assigned", "Substitute Assigned"
        TIME_OFF_APPROVED = "time_off_approved", "Teacher Time Off Approved"
        TIME_OFF_DENIED = "time_off_denied", "Teacher Time Off Denied"
        PAYMENT_RECEIVED = "payment_received", "Payment Received"
        PAYMENT_FAILED = "payment_failed", "Payment Failed"
        PAST_DUE = "past_due", "Account Past Due"
        BALANCE_THRESHOLD = "balance_threshold", "Balance Reaches an Amount"
        UPCOMING_PAYMENT = "upcoming_payment", "Upcoming Payment"
        REGISTRATION_PAYMENT_COMPLETE = "registration_payment_complete", "Registration Payment Completed"
        COSTUME_ASSIGNED = "costume_assigned", "Costume Assigned"
        MEASUREMENT_MISSING = "measurement_missing", "Measurement Missing"
        PERFORMANCE_APPROACHING = "performance_approaching", "Performance Approaching"
        CUSTOM = "custom", "Custom / Future Rule"

    class TimingMode(models.TextChoices):
        IMMEDIATE = "immediate", "Immediately"
        DELAY = "delay", "After a Delay"
        RELATIVE = "relative", "Relative to a Date"
        SCHEDULED = "scheduled", "Scheduled"

    class OffsetDirection(models.TextChoices):
        BEFORE = "before", "Before"
        AFTER = "after", "After"

    class OffsetUnit(models.TextChoices):
        DAYS = "days", "Days"
        WEEKS = "weeks", "Weeks"
        MONTHS = "months", "Months"

    class AudienceType(models.TextChoices):
        CONTEXT_GUARDIANS = "context_guardians", "Parents / Guardians Related to Trigger"
        CONTEXT_GUARDIANS_STUDENTS = "context_guardians_students", "Parents / Guardians + Student"
        CONTEXT_INSTRUCTOR = "context_instructor", "Instructor Related to Trigger"
        ALL_FAMILIES = "all_families", "All Families"
        ALL_INSTRUCTORS = "all_instructors", "All Instructors"
        ALL_ADMINS = "all_admins", "All Administrators"

    studio = models.ForeignKey(Studio, on_delete=models.CASCADE, related_name="email_automation_rules")
    template = models.ForeignKey(EmailTemplate, on_delete=models.CASCADE, related_name="automation_rules")
    name = models.CharField(max_length=180, blank=True)
    enabled = models.BooleanField(default=False)
    trigger_type = models.CharField(max_length=50, choices=TriggerType.choices, default=TriggerType.STUDENT_ENROLLED)
    timing_mode = models.CharField(max_length=20, choices=TimingMode.choices, default=TimingMode.IMMEDIATE)
    audience_type = models.CharField(max_length=40, choices=AudienceType.choices, default=AudienceType.CONTEXT_GUARDIANS)
    threshold_value = models.PositiveIntegerField(null=True, blank=True)
    threshold_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    delay_minutes = models.PositiveIntegerField(default=0)
    offset_value = models.PositiveIntegerField(null=True, blank=True)
    offset_direction = models.CharField(max_length=10, choices=OffsetDirection.choices, default=OffsetDirection.BEFORE)
    offset_unit = models.CharField(max_length=10, choices=OffsetUnit.choices, default=OffsetUnit.DAYS)
    weekday = models.PositiveSmallIntegerField(null=True, blank=True)
    day_of_month = models.PositiveSmallIntegerField(null=True, blank=True)
    month = models.PositiveSmallIntegerField(null=True, blank=True)
    day_of_month_yearly = models.PositiveSmallIntegerField(null=True, blank=True)
    time_of_day = models.TimeField(null=True, blank=True)
    configuration = models.JSONField(default=dict, blank=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    next_run_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["template__name", "trigger_type", "created_at"]

    def __str__(self):
        return self.name or f"{self.template.name} - {self.get_trigger_type_display()}"

class NotificationPreference(models.Model):
    """Per-user notification choices for one Encore studio workspace."""

    studio = models.ForeignKey(
        Studio,
        on_delete=models.CASCADE,
        related_name="notification_preferences",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="encore_notification_preferences",
    )

    task_assigned = models.BooleanField(default=True)
    task_reassigned = models.BooleanField(default=True)
    task_due_reminder = models.BooleanField(default=True)
    task_due_reminder_days = models.PositiveSmallIntegerField(default=2)
    task_overdue = models.BooleanField(default=True)
    task_creator_completed = models.BooleanField(default=True)

    registration_new = models.BooleanField(default=True)
    extra_work_logged = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["studio", "user"],
                name="unique_notification_preferences_per_workspace",
            )
        ]

    def __str__(self):
        return f"{self.user} · {self.studio} notification preferences"


class WorkspaceNotification(models.Model):
    """General Encore notification for non-announcement workspace events."""

    class Category(models.TextChoices):
        TASK = "task", "Task"
        REGISTRATION = "registration", "Registration"
        TIMEKEEPING = "timekeeping", "Time / Extra Work"
        SYSTEM = "system", "System"

    studio = models.ForeignKey(
        Studio,
        on_delete=models.CASCADE,
        related_name="workspace_notifications",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="encore_workspace_notifications",
    )
    category = models.CharField(
        max_length=30,
        choices=Category.choices,
        default=Category.SYSTEM,
    )
    kind = models.CharField(max_length=60)
    title = models.CharField(max_length=200)
    message = models.TextField(blank=True)
    action_url = models.CharField(max_length=1000, blank=True)
    dedupe_key = models.CharField(max_length=255, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def is_read(self):
        return self.read_at is not None

    def __str__(self):
        return f"{self.user}: {self.title}"



class OutboundEmailLog(models.Model):
    """Snapshot of the exact outbound message; SES acceptance is not delivery."""
    studio = models.ForeignKey("studios.Studio", on_delete=models.CASCADE, related_name="outbound_email_logs", null=True, blank=True)
    to_addresses = models.JSONField(default=list)
    cc_addresses = models.JSONField(default=list, blank=True)
    bcc_addresses = models.JSONField(default=list, blank=True)
    sender = models.CharField(max_length=320)
    reply_to_addresses = models.JSONField(default=list, blank=True)
    subject = models.TextField()
    text_body = models.TextField(blank=True)
    html_body = models.TextField(blank=True)
    category = models.CharField(max_length=80, blank=True)
    source = models.CharField(max_length=80, blank=True)
    provider_message_id = models.CharField(max_length=255, blank=True, db_index=True)
    status = models.CharField(max_length=30, default="queued", db_index=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    last_event_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["studio", "-created_at"])]

    def __str__(self):
        return f"{self.subject[:70]} ({self.status})"


class OutboundEmailEvent(models.Model):
    email = models.ForeignKey(OutboundEmailLog, on_delete=models.CASCADE, related_name="delivery_events")
    event_type = models.CharField(max_length=40)
    event_key = models.CharField(max_length=255, unique=True)
    occurred_at = models.DateTimeField()
    detail = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-occurred_at"]
