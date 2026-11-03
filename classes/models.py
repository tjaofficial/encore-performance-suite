from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models

from instructors.models import Instructor
from studios.models import Studio, StudioLocation, StudioRoom


class Season(models.Model):
    studio = models.ForeignKey(
        Studio,
        on_delete=models.CASCADE,
        related_name="seasons",
    )

    name = models.CharField(max_length=150)

    start_date = models.DateField()
    end_date = models.DateField()

    registration_opens = models.DateField(
        null=True,
        blank=True,
    )

    registration_closes = models.DateField(
        null=True,
        blank=True,
    )

    is_active = models.BooleanField(default=True)
    registration_open = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-start_date", "name"]

        constraints = [
            models.UniqueConstraint(
                fields=["studio", "name"],
                name="unique_season_name_per_studio",
            )
        ]

    def clean(self):
        super().clean()

        if self.end_date < self.start_date:
            raise ValidationError(
                {"end_date": "Season end date cannot be before start date."}
            )

    def __str__(self):
        return self.name


class ClassType(models.Model):
    studio = models.ForeignKey(
        Studio,
        on_delete=models.CASCADE,
        related_name="class_types",
    )

    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

        constraints = [
            models.UniqueConstraint(
                fields=["studio", "name"],
                name="unique_class_type_name_per_studio",
            )
        ]

    def __str__(self):
        return self.name


class ClassLevel(models.Model):
    studio = models.ForeignKey(
        Studio,
        on_delete=models.CASCADE,
        related_name="class_levels",
    )

    number = models.PositiveSmallIntegerField()
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    aliases = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["number", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["studio", "number"],
                name="unique_class_level_number_per_studio",
            ),
            models.UniqueConstraint(
                fields=["studio", "name"],
                name="unique_class_level_name_per_studio",
            ),
        ]

    def clean(self):
        super().clean()
        cleaned = []
        seen = set()
        for value in self.aliases or []:
            alias = str(value or "").strip()
            key = alias.lower()
            if alias and key not in seen:
                cleaned.append(alias)
                seen.add(key)
        self.aliases = cleaned

    def __str__(self):
        return f"Level {self.number} — {self.name}"


class Class(models.Model):
    class RegistrationMode(models.TextChoices):
        ONLINE = "online", "Online registration"
        APPROVAL = "approval", "In-person approval required"

    registration_mode = models.CharField(
        max_length=20, choices=RegistrationMode.choices,
        default=RegistrationMode.ONLINE,
        help_text="Require a studio-issued approval code before online registration.",
    )
    class GenderRestriction(models.TextChoices):
        ANY = "any", "Any"
        FEMALE = "female", "Female"
        MALE = "male", "Male"
        OTHER = "other", "Other / Studio Defined"

    studio = models.ForeignKey(
        Studio,
        on_delete=models.CASCADE,
        related_name="classes",
    )

    season = models.ForeignKey(
        Season,
        on_delete=models.PROTECT,
        related_name="classes",
    )

    class_type = models.ForeignKey(
        ClassType,
        on_delete=models.PROTECT,
        related_name="classes",
    )

    level = models.ForeignKey(
        ClassLevel,
        on_delete=models.PROTECT,
        related_name="classes",
        null=True,
        blank=True,
    )

    class_id = models.CharField(
        max_length=50,
    )

    name = models.CharField(
        max_length=200,
    )

    description = models.TextField(
        blank=True,
    )

    dress_code = models.TextField(
        blank=True,
        help_text=(
            "Optional class-specific attire, shoes, hair, "
            "or appearance requirements."
        ),
    )

    instructor = models.ForeignKey(
        Instructor,
        on_delete=models.PROTECT,
        related_name="primary_classes",
    )

    assistant_instructor = models.ForeignKey(
        Instructor,
        on_delete=models.PROTECT,
        related_name="assistant_classes",
        null=True,
        blank=True,
    )

    default_location = models.ForeignKey(
        StudioLocation,
        on_delete=models.SET_NULL,
        related_name="classes",
        null=True,
        blank=True,
    )

    capacity = models.PositiveIntegerField(
        default=20,
    )

    min_age = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )

    max_age = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )

    is_performance_class = models.BooleanField(
        null=True,
        blank=True,
        default=None,
        help_text=(
            "Performance class, non-performance class, or unknown. "
            "Unknown is useful while imported data is being reviewed."
        ),
    )

    gender_restriction = models.CharField(
        max_length=20,
        choices=GenderRestriction.choices,
        default=GenderRestriction.ANY,
    )

    prerequisites = models.ManyToManyField(
        "self",
        symmetrical=False,
        blank=True,
    )

    allow_drop_ins = models.BooleanField(
        default=False,
    )

    drop_in_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )

    # SOURCE OF TRUTH FOR NORMAL CLASS TUITION PRICE.
    tuition_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )

    # Billing policy controls HOW the class price is billed.
    # The policy amount is NOT used for class enrollment billing.
    tuition_plan = models.ForeignKey(
        "billing.TuitionPlan",
        on_delete=models.PROTECT,
        related_name="classes",
        null=True,
        blank=True,
        help_text=(
            "Controls billing frequency, late fee, grace period, "
            "and registration fee. Tuition price comes from this Class."
        ),
    )

    is_active = models.BooleanField(
        default=True,
    )

    registration_open = models.BooleanField(
        default=True,
    )

    registration_opens = models.DateField(
        null=True,
        blank=True,
        help_text=(
            "Optional class-specific registration opening date. "
            "Leave blank to rely on the studio/season registration setup."
        ),
    )

    registration_closes = models.DateField(
        null=True,
        blank=True,
        help_text=(
            "Optional class-specific registration closing date. "
            "Leave blank to rely on the studio/season registration setup."
        ),
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
        ordering = ["name"]

        constraints = [
            models.UniqueConstraint(
                fields=["studio", "class_id"],
                name="unique_class_id_per_studio",
            )
        ]

    @staticmethod
    def _age_display(value):
        if value is None:
            return ""

        value = Decimal(str(value))
        if value == Decimal("1.50"):
            return "18 months"

        if value == value.to_integral():
            return str(int(value))

        normalized = format(value.normalize(), "f")
        return normalized.rstrip("0").rstrip(".")

    @property
    def age_range_label(self):
        minimum = self._age_display(self.min_age)
        maximum = self._age_display(self.max_age)

        if minimum and maximum:
            return f"{minimum}–{maximum}"
        if minimum:
            return f"{minimum}+"
        if maximum:
            return f"Up to {maximum}"
        return "Any age"

    def standardized_name(self):
        type_name = (
            self.class_type.name.strip()
            if self.class_type_id
            else ""
        )
        level_name = (
            self.level.name.strip()
            if self.level_id
            else ""
        )

        if type_name and level_name:
            return f"{type_name} - {level_name}"
        return type_name or self.name

    @property
    def current_enrollment_count(self):
        return self.enrollments.filter(
            status="active",
        ).count()

    @property
    def available_slots(self):
        return max(
            self.capacity - self.current_enrollment_count,
            0,
        )

    @property
    def is_full(self):
        return self.current_enrollment_count >= self.capacity

    def clean(self):
        super().clean()

        if self.season_id and self.season.studio_id != self.studio_id:
            raise ValidationError(
                {"season": "Season must belong to the same studio."}
            )

        if (
            self.class_type_id
            and self.class_type.studio_id != self.studio_id
        ):
            raise ValidationError(
                {"class_type": "Class type must belong to the same studio."}
            )

        if (
            self.level_id
            and self.level.studio_id != self.studio_id
        ):
            raise ValidationError(
                {"level": "Class level must belong to the same studio."}
            )

        if (
            self.instructor_id
            and self.instructor.studio_id != self.studio_id
        ):
            raise ValidationError(
                {"instructor": "Instructor must belong to the same studio."}
            )

        if (
            self.assistant_instructor_id
            and self.assistant_instructor.studio_id != self.studio_id
        ):
            raise ValidationError(
                {
                    "assistant_instructor": (
                        "Assistant instructor must belong to the same studio."
                    )
                }
            )

        if (
            self.default_location_id
            and self.default_location.studio_id != self.studio_id
        ):
            raise ValidationError(
                {
                    "default_location": (
                        "Location must belong to the same studio."
                    )
                }
            )

        if (
            self.tuition_plan_id
            and self.tuition_plan.studio_id != self.studio_id
        ):
            raise ValidationError(
                {
                    "tuition_plan": (
                        "Tuition policy must belong to the same studio."
                    )
                }
            )

        if (
            self.min_age is not None
            and self.max_age is not None
            and self.max_age < self.min_age
        ):
            raise ValidationError(
                {"max_age": "Maximum age cannot be less than minimum age."}
            )

        if (
            self.registration_opens
            and self.registration_closes
            and self.registration_closes < self.registration_opens
        ):
            raise ValidationError(
                {
                    "registration_closes": (
                        "Registration closing date cannot be before "
                        "the opening date."
                    )
                }
            )

        if (
            self.tuition_amount is not None
            and self.tuition_amount < Decimal("0.00")
        ):
            raise ValidationError(
                {"tuition_amount": "Tuition cannot be negative."}
            )

    def __str__(self):
        return f"{self.class_id} - {self.name}"


class ClassMeeting(models.Model):
    class DayOfWeek(models.IntegerChoices):
        MONDAY = 0, "Monday"
        TUESDAY = 1, "Tuesday"
        WEDNESDAY = 2, "Wednesday"
        THURSDAY = 3, "Thursday"
        FRIDAY = 4, "Friday"
        SATURDAY = 5, "Saturday"
        SUNDAY = 6, "Sunday"

    class_instance = models.ForeignKey(
        Class,
        on_delete=models.CASCADE,
        related_name="meeting_times",
    )

    day_of_week = models.IntegerField(
        choices=DayOfWeek.choices,
    )

    start_time = models.TimeField()

    duration_minutes = models.PositiveIntegerField(
        default=60,
    )

    room = models.ForeignKey(
        StudioRoom,
        on_delete=models.SET_NULL,
        related_name="class_meetings",
        null=True,
        blank=True,
    )

    # Legacy compatibility field. New scheduling should use room.
    # When a selected room belongs to a physical location,
    # ClassMeetingForm automatically mirrors that location here.
    location = models.ForeignKey(
        StudioLocation,
        on_delete=models.SET_NULL,
        related_name="class_meetings",
        null=True,
        blank=True,
    )

    is_active = models.BooleanField(
        default=True,
    )

    notes = models.TextField(
        blank=True,
    )

    class Meta:
        ordering = ["day_of_week", "start_time"]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "class_instance",
                    "day_of_week",
                    "start_time",
                ],
                name="unique_class_meeting_time",
            )
        ]

    def clean(self):
        super().clean()

        if (
            self.room_id
            and self.room.studio_id
            != self.class_instance.studio_id
        ):
            raise ValidationError(
                {
                    "room": (
                        "Room must belong to the same studio as the class."
                    )
                }
            )

        if (
            self.location_id
            and self.location.studio_id
            != self.class_instance.studio_id
        ):
            raise ValidationError(
                {"location": "Location must belong to the same studio."}
            )

    def __str__(self):
        return (
            f"{self.class_instance} - "
            f"{self.get_day_of_week_display()} "
            f"{self.start_time}"
        )
