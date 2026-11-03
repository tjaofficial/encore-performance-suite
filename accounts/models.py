from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    email = models.EmailField(unique=True)
    email_verification_required = models.BooleanField(default=False)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    email_verification_token = models.UUIDField(null=True, blank=True, unique=True)
    email_verification_sent_at = models.DateTimeField(null=True, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    def __str__(self):
        return self.email


class DashboardPreference(models.Model):
    class DashboardType(models.TextChoices):
        CLASS = "class_dashboard", "Class Dashboard"
        TEACHER = "teacher_dashboard", "Teacher Dashboard"
        ADMIN = "admin_dashboard", "Admin Dashboard"

    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="dashboard_preferences",
    )

    studio = models.ForeignKey(
        "studios.Studio",
        on_delete=models.CASCADE,
        related_name="dashboard_preferences",
    )

    dashboard_type = models.CharField(
        max_length=40,
        choices=DashboardType.choices,
    )

    layout = models.JSONField(
        default=dict,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "studio", "dashboard_type"],
                name="unique_user_studio_dashboard_preference",
            )
        ]

    def __str__(self):
        return (
            f"{self.user} - {self.studio} - "
            f"{self.get_dashboard_type_display()}"
        )
