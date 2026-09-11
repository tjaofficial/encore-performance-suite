from django.core.exceptions import ValidationError
from django.db import models

from classes.models import Class
from instructors.models import Instructor
from studios.models import Studio


class ChoreographyPlan(models.Model):
    studio = models.ForeignKey(
        Studio,
        on_delete=models.CASCADE,
        related_name="choreography_plans",
    )

    class_instance = models.ForeignKey(
        Class,
        on_delete=models.CASCADE,
        related_name="choreography_plans",
    )

    title = models.CharField(
        max_length=200,
        blank=True,
    )

    song_title = models.CharField(
        max_length=200,
        blank=True,
    )

    artist = models.CharField(
        max_length=200,
        blank=True,
    )

    music_resource = models.ForeignKey(
        "resources.ClassResource",
        on_delete=models.SET_NULL,
        related_name="dances",
        null=True,
        blank=True,
        limit_choices_to={
            "resource_type": "music",
        },
    )

    choreography_notes = models.TextField(
        blank=True,
    )

    teacher_notes = models.TextField(
        blank=True,
    )

    performance_notes = models.TextField(
        blank=True,
    )

    created_by = models.ForeignKey(
        Instructor,
        on_delete=models.SET_NULL,
        related_name="created_choreography_plans",
        null=True,
        blank=True,
    )

    updated_by = models.ForeignKey(
        Instructor,
        on_delete=models.SET_NULL,
        related_name="updated_choreography_plans",
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
            "class_instance__name",
        ]

    def clean(self):
        super().clean()

        if (
            self.class_instance_id
            and self.class_instance.studio_id != self.studio_id
        ):
            raise ValidationError(
                {
                    "class_instance": (
                        "Class must belong to the same studio."
                    )
                }
            )

        if self.music_resource_id:
            if self.music_resource.studio_id != self.studio_id:
                raise ValidationError(
                    {
                        "music_resource": (
                            "Song must belong to the same studio."
                        )
                    }
                )

            if (
                self.music_resource.class_instance_id
                != self.class_instance_id
            ):
                raise ValidationError(
                    {
                        "music_resource": (
                            "Song must belong to the same class."
                        )
                    }
                )

            if (
                self.music_resource.resource_type
                != self.music_resource.ResourceType.MUSIC
            ):
                raise ValidationError(
                    {
                        "music_resource": (
                            "Selected resource must be music."
                        )
                    }
                )

    def __str__(self):
        return (
            self.title
            or f"{self.class_instance.name} Choreography"
        )


class DrawingBoard(models.Model):
    studio = models.ForeignKey(Studio, on_delete=models.CASCADE, related_name="drawing_boards")
    class_instance = models.ForeignKey(
        Class,
        on_delete=models.CASCADE,
        related_name="drawing_boards",
    )

    performance_plan = models.ForeignKey(
        ChoreographyPlan,
        on_delete=models.SET_NULL,
        related_name="drawing_boards",
        null=True,
        blank=True,
    )
    title = models.CharField(max_length=200, blank=True)
    song_duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    marker_assignments = models.JSONField(default=list, blank=True)
    stage_drawings = models.JSONField(
        default=list,
        blank=True,
        help_text="Persistent stage/performance-space drawings for this Drawing Board.",
    )
    show_offstage_wings = models.BooleanField(default=False)
    apron_stage_grid = models.BooleanField(
        default=False,
        help_text="Render the Drawing Board as a proscenium stage with an apron.",
    )
    created_by = models.ForeignKey(Instructor, on_delete=models.SET_NULL, related_name="created_drawing_boards", null=True, blank=True)
    updated_by = models.ForeignKey(Instructor, on_delete=models.SET_NULL, related_name="updated_drawing_boards", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        super().clean()
        if self.class_instance_id and self.class_instance.studio_id != self.studio_id:
            raise ValidationError({"class_instance": "Class must belong to the same studio."})
        if self.performance_plan_id and self.performance_plan.studio_id != self.studio_id:
            raise ValidationError({"performance_plan": "Performance Plan must belong to the same studio."})
        if self.performance_plan_id and self.performance_plan.class_instance_id != self.class_instance_id:
            raise ValidationError({"performance_plan": "Performance Plan must belong to the same class."})

    def __str__(self):
        return self.title or f"{self.class_instance.name} Drawing Board"


class Formation(models.Model):
    board = models.ForeignKey(
        DrawingBoard,
        on_delete=models.CASCADE,
        related_name="formations",
        null=True,
        blank=True,
    )

    plan = models.ForeignKey(
        ChoreographyPlan,
        on_delete=models.CASCADE,
        related_name="formations",
        null=True,
        blank=True,
    )

    name = models.CharField(
        max_length=150,
    )

    section_label = models.CharField(
        max_length=150,
        blank=True,
        help_text=(
            "Example: Intro, Chorus 1, Bridge, Finale"
        ),
    )

    sequence_order = models.PositiveIntegerField(
        default=0,
    )

    time_seconds = models.PositiveIntegerField(
        default=0,
        help_text=(
            "Legacy formation timestamp. Drawing Board playback now "
            "uses hold_duration_seconds and transition durations."
        ),
    )

    hold_duration_seconds = models.PositiveIntegerField(
        default=8,
        help_text=(
            "How long this formation is held before the next transition."
        ),
    )

    notes = models.TextField(
        blank=True,
    )

    # Marker positions are formation-specific.
    # Example: [{"marker": 1, "x": 50, "y": 20}]
    positions = models.JSONField(
        default=list,
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
            "time_seconds",
            "sequence_order",
            "id",
        ]

    def clean(self):
        super().clean()

        song_duration_seconds = (
            self.board.song_duration_seconds
            if self.board_id
            else None
        )

        if (
            song_duration_seconds is not None
            and self.time_seconds > song_duration_seconds
        ):
            raise ValidationError(
                {
                    "time_seconds": (
                        "Formation time cannot be after the end of the song."
                    )
                }
            )

    @property
    def time_display(self):
        minutes, seconds = divmod(self.time_seconds, 60)
        return f"{minutes}:{seconds:02d}"

    def __str__(self):
        return f"{self.board or self.plan} - {self.name}"


class FormationTransition(models.Model):
    board = models.ForeignKey(
        DrawingBoard,
        on_delete=models.CASCADE,
        related_name="formation_transitions",
    )

    from_formation = models.ForeignKey(
        Formation,
        on_delete=models.CASCADE,
        related_name="outgoing_transitions",
    )

    to_formation = models.ForeignKey(
        Formation,
        on_delete=models.CASCADE,
        related_name="incoming_transitions",
    )

    movements = models.JSONField(
        default=list,
        blank=True,
    )

    duration_seconds = models.PositiveIntegerField(
        default=3,
        help_text=(
            "How long dancers take to move from the earlier formation "
            "to the later formation."
        ),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "board",
                    "from_formation",
                    "to_formation",
                ],
                name="unique_formation_transition_pair",
            ),
        ]

    def clean(self):
        super().clean()

        if (
            self.from_formation_id
            and self.from_formation.board_id != self.board_id
        ):
            raise ValidationError({
                "from_formation": (
                    "Starting formation must belong to this Drawing Board."
                )
            })

        if (
            self.to_formation_id
            and self.to_formation.board_id != self.board_id
        ):
            raise ValidationError({
                "to_formation": (
                    "Ending formation must belong to this Drawing Board."
                )
            })

        if (
            self.from_formation_id
            and self.to_formation_id
            and self.from_formation_id == self.to_formation_id
        ):
            raise ValidationError({
                "to_formation": (
                    "A transition must connect two different formations."
                )
            })

    def __str__(self):
        return (
            f"{self.board} - "
            f"{self.from_formation.name} → "
            f"{self.to_formation.name}"
        )


class DrawingBoardLightingFixture(models.Model):
    class FixtureType(models.TextChoices):
        PAR = "par", "PAR"
        ELLIPSOIDAL = "ellipsoidal", "Ellipsoidal / Profile"
        FRESNEL = "fresnel", "Fresnel"
        CYC = "cyc", "Cyc / Strip"
        FOLLOW_SPOT = "follow_spot", "Follow Spot"

    board = models.ForeignKey(
        DrawingBoard,
        on_delete=models.CASCADE,
        related_name="lighting_fixtures",
    )
    fixture_number = models.PositiveIntegerField(default=1)
    label = models.CharField(max_length=100, blank=True)
    fixture_type = models.CharField(
        max_length=30,
        choices=FixtureType.choices,
        default=FixtureType.PAR,
    )
    x = models.DecimalField(max_digits=6, decimal_places=3, default=50)
    y = models.DecimalField(max_digits=6, decimal_places=3, default=10)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        Instructor,
        on_delete=models.SET_NULL,
        related_name="created_drawing_board_lighting_fixtures",
        null=True,
        blank=True,
    )
    updated_by = models.ForeignKey(
        Instructor,
        on_delete=models.SET_NULL,
        related_name="updated_drawing_board_lighting_fixtures",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["fixture_number", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["board", "fixture_number"],
                name="unique_drawing_board_fixture_number",
            ),
        ]

    def __str__(self):
        return self.label or f"Fixture {self.fixture_number} · {self.get_fixture_type_display()}"


class DrawingBoardLightingCue(models.Model):
    board = models.ForeignKey(
        DrawingBoard,
        on_delete=models.CASCADE,
        related_name="lighting_cues",
    )

    cue_number = models.PositiveIntegerField(
        default=1,
    )

    name = models.CharField(
        max_length=150,
        blank=True,
    )

    time_seconds = models.PositiveIntegerField(
        default=0,
        help_text=(
            "Independent song time when this lighting cue begins."
        ),
    )

    fade_seconds = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=1.00,
        help_text=(
            "Fade time into this cue, in seconds."
        ),
    )

    is_blackout = models.BooleanField(
        default=False,
    )

    focus_areas = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "Simple-mode lighting focus areas positioned on the stage."
        ),
    )

    follow_spots = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "Simple-mode follow spots targeting dancer markers "
            "or fixed stage positions."
        ),
    )

    fixture_states = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "Pro-mode per-cue settings for persistent Drawing Board fixtures."
        ),
    )

    notes = models.TextField(
        blank=True,
    )

    created_by = models.ForeignKey(
        Instructor,
        on_delete=models.SET_NULL,
        related_name="created_drawing_board_lighting_cues",
        null=True,
        blank=True,
    )

    updated_by = models.ForeignKey(
        Instructor,
        on_delete=models.SET_NULL,
        related_name="updated_drawing_board_lighting_cues",
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
            "time_seconds",
            "cue_number",
            "id",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "board",
                    "cue_number",
                ],
                name="unique_drawing_board_lighting_cue_number",
            ),
        ]

    @property
    def time_display(self):
        minutes, seconds = divmod(
            self.time_seconds,
            60,
        )
        return f"{minutes}:{seconds:02d}"

    def __str__(self):
        return (
            f"{self.board} - LX {self.cue_number} "
            f"{self.name or 'Lighting Cue'}"
        )


class LightingCue(models.Model):
    plan = models.ForeignKey(
        ChoreographyPlan,
        on_delete=models.CASCADE,
        related_name="lighting_cues",
    )

    cue_number = models.PositiveIntegerField()

    name = models.CharField(
        max_length=150,
    )

    timing = models.CharField(
        max_length=100,
        blank=True,
        help_text=(
            "Example: 0:32, first chorus, after blackout"
        ),
    )

    color_notes = models.CharField(
        max_length=200,
        blank=True,
    )

    action = models.TextField(
        blank=True,
    )

    notes = models.TextField(
        blank=True,
    )

    class Meta:
        ordering = [
            "cue_number",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "plan",
                    "cue_number",
                ],
                name="unique_lighting_cue_number_per_plan",
            )
        ]

    def __str__(self):
        return f"Cue {self.cue_number} - {self.name}"


class PerformancePrepItem(models.Model):
    class Category(models.TextChoices):
        COSTUME = "costume", "Costume"
        PROP = "prop", "Prop"
        MUSIC = "music", "Music"
        LIGHTING = "lighting", "Lighting"
        STAGING = "staging", "Staging"
        ADMIN = "admin", "Administrative"
        OTHER = "other", "Other"

    plan = models.ForeignKey(
        ChoreographyPlan,
        on_delete=models.CASCADE,
        related_name="prep_items",
    )

    category = models.CharField(
        max_length=20,
        choices=Category.choices,
        default=Category.OTHER,
    )

    title = models.CharField(
        max_length=200,
    )

    notes = models.TextField(
        blank=True,
    )

    due_date = models.DateField(
        null=True,
        blank=True,
    )

    is_complete = models.BooleanField(
        default=False,
    )

    sort_order = models.PositiveIntegerField(
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
            "is_complete",
            "sort_order",
            "due_date",
            "id",
        ]

    def __str__(self):
        return self.title
