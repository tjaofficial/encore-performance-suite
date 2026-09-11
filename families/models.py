from django.conf import settings
from django.db import models

from studios.models import Studio


class Family(models.Model):
    studio = models.ForeignKey(
        Studio,
        on_delete=models.CASCADE,
        related_name="families",
    )

    family_name = models.CharField(
        max_length=255,
        blank=True,
    )

    primary_contact_first_name = models.CharField(
        max_length=100,
        blank=True,
    )

    primary_contact_last_name = models.CharField(
        max_length=100,
        blank=True,
    )

    primary_email = models.EmailField(
        blank=True,
    )

    secondary_email = models.EmailField(
        blank=True,
    )

    primary_phone = models.CharField(
        max_length=50,
        blank=True,
    )

    secondary_phone = models.CharField(
        max_length=50,
        blank=True,
    )

    address_line_1 = models.CharField(
        max_length=255,
        blank=True,
    )

    address_line_2 = models.CharField(
        max_length=255,
        blank=True,
    )

    city = models.CharField(
        max_length=100,
        blank=True,
    )

    state = models.CharField(
        max_length=100,
        blank=True,
    )

    postal_code = models.CharField(
        max_length=20,
        blank=True,
    )

    emergency_contact_name = models.CharField(
        max_length=255,
        blank=True,
    )

    emergency_contact_phone = models.CharField(
        max_length=50,
        blank=True,
    )

    emergency_contact_relationship = models.CharField(
        max_length=100,
        blank=True,
    )

    how_did_you_hear_about_us = models.CharField(
        max_length=255,
        blank=True,
    )

    notes = models.TextField(
        blank=True,
    )

    is_active = models.BooleanField(
        default=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    def __str__(self):
        if self.family_name:
            return self.family_name

        full_name = (
            f"{self.primary_contact_first_name} "
            f"{self.primary_contact_last_name}"
        ).strip()

        return full_name or f"Family #{self.pk}"

class Guardian(models.Model):
    family = models.ForeignKey(
        Family,
        on_delete=models.CASCADE,
        related_name="guardians",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="guardian_profiles",
        null=True,
        blank=True,
    )

    first_name = models.CharField(
        max_length=100,
    )

    last_name = models.CharField(
        max_length=100,
    )

    relationship = models.CharField(
        max_length=100,
        blank=True,
    )

    email = models.EmailField(
        blank=True,
    )

    phone = models.CharField(
        max_length=50,
        blank=True,
    )

    is_primary = models.BooleanField(
        default=False,
    )

    is_authorized_for_pickup = models.BooleanField(
        default=True,
    )

    is_financially_responsible = models.BooleanField(
        default=False,
    )

    is_active = models.BooleanField(
        default=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    def __str__(self):
        return f"{self.first_name} {self.last_name}"