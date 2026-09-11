from datetime import date
from django.core.exceptions import ValidationError
from django.conf import settings
from django.db import models

from families.models import Family
from studios.models import Studio


class Student(models.Model):
    class Gender(models.TextChoices):
        FEMALE = "female", "Female"
        MALE = "male", "Male"

    studio = models.ForeignKey(
        Studio,
        on_delete=models.CASCADE,
        related_name="students",
    )

    family = models.ForeignKey(
        Family,
        on_delete=models.SET_NULL,
        related_name="students",
        null=True,
        blank=True,
    )

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="student_profile",
        null=True,
        blank=True,
    )

    first_name = models.CharField(
        max_length=100,
    )

    last_name = models.CharField(
        max_length=100,
    )

    birthday = models.DateField()

    gender = models.CharField(
        max_length=30,
        choices=Gender.choices,
        blank=True,
    )

    medical_conditions = models.TextField(
        blank=True,
    )

    allergies = models.TextField(
        blank=True,
    )

    comments = models.TextField(
        blank=True,
    )

    paper_waiver_on_file = models.BooleanField(
        default=False,
    )

    performing = models.BooleanField(
        default=True,
    )

    is_active = models.BooleanField(
        default=True,
    )

    enrollment_blocked = models.BooleanField(
        default=False,
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

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    @property
    def age(self):
        today = date.today()

        return (
            today.year
            - self.birthday.year
            - (
                (today.month, today.day)
                < (self.birthday.month, self.birthday.day)
            )
        )

    @property
    def is_birthday_today(self):
        today = date.today()

        return (
            self.birthday.month == today.month
            and self.birthday.day == today.day
        )

    @property
    def is_minor(self):
        return self.age < 18

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    def clean(self):
        super().clean()

        if self.is_minor and self.family is None:
            raise ValidationError(
                {
                    "family": (
                        "Students under 18 must be assigned to a family or guardian."
                    )
                }
            )