import uuid
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from classes.models import Class
from studios.models import Studio


class RegistrationRequest(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "New"
        CONTACTED = "contacted", "Contacted"
        CONVERTED = "converted", "Converted"
        CLOSED = "closed", "Closed"

    studio = models.ForeignKey(
        Studio,
        on_delete=models.CASCADE,
        related_name="registration_requests",
    )

    class_instance = models.ForeignKey(
        Class,
        on_delete=models.PROTECT,
        related_name="registration_requests",
    )

    guardian_first_name = models.CharField(max_length=100)
    guardian_last_name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=40, blank=True)

    student_first_name = models.CharField(max_length=100)
    student_last_name = models.CharField(max_length=100)
    student_birthday = models.DateField()

    notes = models.TextField(blank=True)

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NEW,
    )

    linked_family = models.ForeignKey(
        "families.Family",
        on_delete=models.SET_NULL,
        related_name="registration_requests",
        null=True,
        blank=True,
    )

    linked_student = models.ForeignKey(
        "students.Student",
        on_delete=models.SET_NULL,
        related_name="registration_requests",
        null=True,
        blank=True,
    )

    linked_enrollment = models.ForeignKey(
        "enrollments.Enrollment",
        on_delete=models.SET_NULL,
        related_name="registration_requests",
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def clean(self):
        super().clean()

        if (
            self.class_instance_id
            and self.class_instance.studio_id != self.studio_id
        ):
            raise ValidationError(
                {
                    "class_instance": (
                        "Class must belong to the selected studio."
                    )
                }
            )

    def __str__(self):
        return (
            f"{self.student_first_name} "
            f"{self.student_last_name} - "
            f"{self.class_instance}"
        )


class FamilyInvite(models.Model):
    studio = models.ForeignKey(
        Studio,
        on_delete=models.CASCADE,
        related_name="family_invites",
    )

    email = models.EmailField()

    guardian_first_name = models.CharField(
        max_length=100,
        blank=True,
    )

    guardian_last_name = models.CharField(
        max_length=100,
        blank=True,
    )

    family = models.ForeignKey(
        "families.Family",
        on_delete=models.CASCADE,
        related_name="invites",
        null=True,
        blank=True,
    )

    token = models.CharField(
        max_length=80,
        unique=True,
        editable=False,
    )

    expires_at = models.DateTimeField()

    accepted_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="created_family_invites",
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = [
            "-created_at",
        ]

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_urlsafe(32)

        if not self.expires_at:
            self.expires_at = (
                timezone.now()
                + timedelta(days=7)
            )

        super().save(*args, **kwargs)

    @property
    def is_expired(self):
        return (
            self.expires_at
            <= timezone.now()
        )

    @property
    def is_accepted(self):
        return self.accepted_at is not None

    @property
    def is_usable(self):
        return (
            not self.is_accepted
            and not self.is_expired
        )

    def __str__(self):
        return f"{self.email} - {self.studio}"


def registration_session_expires_at():
    return timezone.now() + timedelta(hours=48)


class PublicRegistrationSession(models.Model):
    class RegistrationType(models.TextChoices):
        SELF = "self", "I am registering myself"
        STUDENT = "student", "I am registering a student"

    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "In Progress"
        READY_FOR_PAYMENT = "ready_for_payment", "Ready for Payment"
        PAYMENT_PENDING = "payment_pending", "Payment Pending"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"
        EXPIRED = "expired", "Expired"

    studio = models.ForeignKey(
        Studio,
        on_delete=models.CASCADE,
        related_name="public_registration_sessions",
    )

    token = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
    )

    registration_type = models.CharField(
        max_length=20,
        choices=RegistrationType.choices,
        blank=True,
    )

    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.IN_PROGRESS,
    )

    current_step = models.CharField(
        max_length=30,
        default="type",
    )

    contact_email = models.EmailField(
        blank=True,
    )

    account_data = models.JSONField(
        default=dict,
        blank=True,
    )

    student_data = models.JSONField(
        default=dict,
        blank=True,
    )

    selected_classes = models.ManyToManyField(
        Class,
        related_name="public_registration_sessions",
        blank=True,
    )

    pricing_snapshot = models.JSONField(
        default=dict,
        blank=True,
    )

    embed_mode = models.BooleanField(
        default=False,
    )

    stripe_payment_intent_id = models.CharField(
        max_length=255,
        blank=True,
    )

    linked_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="completed_public_registrations",
        null=True,
        blank=True,
    )

    linked_family = models.ForeignKey(
        "families.Family",
        on_delete=models.SET_NULL,
        related_name="public_registration_sessions",
        null=True,
        blank=True,
    )

    linked_student = models.ForeignKey(
        "students.Student",
        on_delete=models.SET_NULL,
        related_name="public_registration_sessions",
        null=True,
        blank=True,
    )

    linked_payment = models.ForeignKey(
        "billing.Payment",
        on_delete=models.SET_NULL,
        related_name="public_registration_sessions",
        null=True,
        blank=True,
    )

    expires_at = models.DateTimeField(
        default=registration_session_expires_at,
    )

    finalized_at = models.DateTimeField(
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
            "-updated_at",
        ]

    @property
    def is_expired(self):
        return (
            self.expires_at <= timezone.now()
            and self.status
            not in {
                self.Status.COMPLETED,
                self.Status.CANCELLED,
            }
        )

    def mark_expired(self):
        if self.is_expired and self.status != self.Status.EXPIRED:
            self.status = self.Status.EXPIRED
            self.save(
                update_fields=[
                    "status",
                    "updated_at",
                ]
            )

    def touch(self):
        self.expires_at = registration_session_expires_at()
        self.save(
            update_fields=[
                "expires_at",
                "updated_at",
            ]
        )

    def __str__(self):
        return (
            f"{self.studio.name} registration "
            f"{self.token}"
        )


class RegistrationClassHold(models.Model):
    registration_session = models.ForeignKey(
        PublicRegistrationSession,
        on_delete=models.CASCADE,
        related_name="class_holds",
    )

    class_instance = models.ForeignKey(
        Class,
        on_delete=models.CASCADE,
        related_name="registration_holds",
    )

    expires_at = models.DateTimeField()
    is_active = models.BooleanField(
        default=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "registration_session",
                    "class_instance",
                ],
                name="unique_registration_class_hold",
            )
        ]

    @property
    def is_expired(self):
        return self.expires_at <= timezone.now()

    def __str__(self):
        return (
            f"{self.registration_session.token} - "
            f"{self.class_instance}"
        )
