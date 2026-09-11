from django.conf import settings
from django.db import models

from studios.models import Studio


class Instructor(models.Model):
    studio = models.ForeignKey(
        Studio,
        on_delete=models.CASCADE,
        related_name="instructors",
    )

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="instructor_profile",
        null=True,
        blank=True,
    )

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)

    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)

    address_line_1 = models.CharField(max_length=255, blank=True)
    address_line_2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)

    emergency_contact_name = models.CharField(max_length=255, blank=True)
    emergency_contact_phone = models.CharField(max_length=50, blank=True)
    emergency_contact_relationship = models.CharField(max_length=100, blank=True)

    bio = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def __str__(self):
        return self.full_name


class InstructorAvailability(models.Model):
    class DayOfWeek(models.IntegerChoices):
        MONDAY = 0, "Monday"
        TUESDAY = 1, "Tuesday"
        WEDNESDAY = 2, "Wednesday"
        THURSDAY = 3, "Thursday"
        FRIDAY = 4, "Friday"
        SATURDAY = 5, "Saturday"
        SUNDAY = 6, "Sunday"

    instructor = models.ForeignKey(
        Instructor,
        on_delete=models.CASCADE,
        related_name="availability",
    )

    day_of_week = models.PositiveSmallIntegerField(
        choices=DayOfWeek.choices,
    )

    start_time = models.TimeField()
    end_time = models.TimeField()
    is_available = models.BooleanField(default=True)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["day_of_week", "start_time"]
        constraints = [
            models.UniqueConstraint(
                fields=["instructor", "day_of_week", "start_time", "end_time"],
                name="unique_instructor_availability_window",
            )
        ]

    def __str__(self):
        return (
            f"{self.instructor.full_name} - "
            f"{self.get_day_of_week_display()} "
            f"{self.start_time}-{self.end_time}"
        )
