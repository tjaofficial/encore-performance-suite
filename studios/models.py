from django.conf import settings
from django.db import models


class Studio(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)

    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)

    timezone = models.CharField(
        max_length=100,
        default="America/Detroit",
    )

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class StudioMembership(models.Model):
    class Role(models.TextChoices):
        ADMINISTRATOR = "administrator", "Administrator"
        TEACHER = "teacher", "Teacher"
        FAMILY = "family", "Family / Guardian"
        STUDENT = "student", "Student"

    studio = models.ForeignKey(
        Studio,
        on_delete=models.CASCADE,
        related_name="memberships",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="studio_memberships",
    )

    role = models.CharField(
        max_length=30,
        choices=Role.choices,
    )

    is_active = models.BooleanField(default=True)

    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["studio", "user", "role"],
                name="unique_studio_user_role",
            )
        ]

    def __str__(self):
        return f"{self.user} - {self.studio} - {self.get_role_display()}"


class StudioLocation(models.Model):
    studio = models.ForeignKey(
        Studio,
        on_delete=models.CASCADE,
        related_name="locations",
    )

    name = models.CharField(max_length=255)

    address_line_1 = models.CharField(max_length=255)
    address_line_2 = models.CharField(
        max_length=255,
        blank=True,
    )

    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)
    country = models.CharField(
        max_length=100,
        default="United States",
    )

    phone = models.CharField(max_length=50, blank=True)

    is_primary = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.studio.name} - {self.name}"


class StudioRoom(models.Model):
    studio = models.ForeignKey(
        Studio,
        on_delete=models.CASCADE,
        related_name="rooms",
    )

    location = models.ForeignKey(
        StudioLocation,
        on_delete=models.CASCADE,
        related_name="rooms",
        null=True,
        blank=True,
    )

    name = models.CharField(max_length=255)

    capacity = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    notes = models.TextField(blank=True)

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = [
            "name",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "studio",
                    "location",
                    "name",
                ],
                name="unique_room_name_per_location",
            )
        ]

    def clean(self):
        super().clean()

        if (
            self.location_id
            and self.studio_id
            and self.location.studio_id
            != self.studio_id
        ):
            from django.core.exceptions import ValidationError

            raise ValidationError(
                {
                    "location": (
                        "Room location must belong to the same studio."
                    )
                }
            )

    def __str__(self):
        if self.location:
            return f"{self.location.name} - {self.name}"

        return f"{self.studio.name} - {self.name}"


class StudioSettings(models.Model):
    studio = models.OneToOneField(
        Studio,
        on_delete=models.CASCADE,
        related_name="settings",
    )

    allow_online_registration = models.BooleanField(default=True)

    require_guardian_for_minors = models.BooleanField(default=True)

    evaluation_enabled = models.BooleanField(default=False)

    evaluation_frequency_days = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    allow_drop_ins_default = models.BooleanField(default=False)

    dashboard_customization_enabled = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    logo = models.ImageField(
        upload_to="studio_branding/",
        null=True,
        blank=True,
    )

    primary_color = models.CharField(
        max_length=7,
        default="#1663FF",
    )

    accent_color = models.CharField(
        max_length=7,
        default="#0197FC",
    )

    public_registration_enabled = models.BooleanField(
        default=True,
    )

    show_capacity_publicly = models.BooleanField(
        default=True,
    )

    allow_waitlist_requests = models.BooleanField(
        default=True,
    )

    public_widget_settings = models.JSONField(
        default=dict,
        blank=True,
    )

    def __str__(self):
        return f"{self.studio.name} Settings"
