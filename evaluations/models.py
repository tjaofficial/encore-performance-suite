from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from classes.models import Class
from instructors.models import Instructor
from students.models import Student
from studios.models import Studio


class EvaluationTemplate(models.Model):
    studio = models.ForeignKey(
        Studio,
        on_delete=models.CASCADE,
        related_name="evaluation_templates",
    )

    name = models.CharField(max_length=150)

    description = models.TextField(blank=True)

    class_type = models.ForeignKey(
        "classes.ClassType",
        on_delete=models.SET_NULL,
        related_name="evaluation_templates",
        null=True,
        blank=True,
    )

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

        constraints = [
            models.UniqueConstraint(
                fields=["studio", "name"],
                name="unique_evaluation_template_name_per_studio",
            )
        ]

    def __str__(self):
        return self.name


class EvaluationCriterion(models.Model):
    class RatingScale(models.TextChoices):
        FIVE_POINT = "five_point", "1–5"
        THREE_POINT = "three_point", "Needs Work / Developing / Strong"

    template = models.ForeignKey(
        EvaluationTemplate,
        on_delete=models.CASCADE,
        related_name="criteria",
    )

    name = models.CharField(max_length=150)

    description = models.TextField(blank=True)

    sort_order = models.PositiveIntegerField(default=0)

    rating_scale = models.CharField(
        max_length=20,
        choices=RatingScale.choices,
        default=RatingScale.FIVE_POINT,
    )

    is_required = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"{self.template.name} - {self.name}"


class StudentEvaluation(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"

    studio = models.ForeignKey(
        Studio,
        on_delete=models.CASCADE,
        related_name="student_evaluations",
    )

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="evaluations",
    )

    class_instance = models.ForeignKey(
        Class,
        on_delete=models.PROTECT,
        related_name="student_evaluations",
    )

    instructor = models.ForeignKey(
        Instructor,
        on_delete=models.PROTECT,
        related_name="student_evaluations",
    )

    template = models.ForeignKey(
        EvaluationTemplate,
        on_delete=models.PROTECT,
        related_name="student_evaluations",
    )

    evaluation_date = models.DateField(default=timezone.localdate)

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )

    overall_notes = models.TextField(blank=True)

    goals = models.TextField(
        blank=True,
        help_text="Goals or focus areas for the student's next evaluation period.",
    )

    published_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-evaluation_date", "-created_at"]

    def clean(self):
        super().clean()

        if self.student_id and self.student.studio_id != self.studio_id:
            raise ValidationError(
                {"student": "Student must belong to this studio."}
            )

        if (
            self.class_instance_id
            and self.class_instance.studio_id != self.studio_id
        ):
            raise ValidationError(
                {"class_instance": "Class must belong to this studio."}
            )

        if (
            self.instructor_id
            and self.instructor.studio_id != self.studio_id
        ):
            raise ValidationError(
                {"instructor": "Instructor must belong to this studio."}
            )

        if (
            self.template_id
            and self.template.studio_id != self.studio_id
        ):
            raise ValidationError(
                {"template": "Template must belong to this studio."}
            )

        if (
            self.student_id
            and self.class_instance_id
            and not self.student.enrollments.filter(
                class_instance=self.class_instance,
                status="active",
            ).exists()
        ):
            raise ValidationError(
                {
                    "student": (
                        "Student must be actively enrolled in the selected class."
                    )
                }
            )

    def publish(self):
        self.status = self.Status.PUBLISHED

        if self.published_at is None:
            self.published_at = timezone.now()

        self.save(
            update_fields=[
                "status",
                "published_at",
                "updated_at",
            ]
        )

    def __str__(self):
        return (
            f"{self.student} - "
            f"{self.class_instance} - "
            f"{self.evaluation_date}"
        )


class EvaluationRating(models.Model):
    evaluation = models.ForeignKey(
        StudentEvaluation,
        on_delete=models.CASCADE,
        related_name="ratings",
    )

    criterion = models.ForeignKey(
        EvaluationCriterion,
        on_delete=models.PROTECT,
        related_name="ratings",
    )

    rating = models.CharField(
        max_length=30,
        blank=True,
    )

    comments = models.TextField(blank=True)

    class Meta:
        ordering = ["criterion__sort_order", "criterion_id"]

        constraints = [
            models.UniqueConstraint(
                fields=["evaluation", "criterion"],
                name="unique_evaluation_criterion_rating",
            )
        ]

    def clean(self):
        super().clean()

        if (
            self.evaluation_id
            and self.criterion_id
            and self.criterion.template_id != self.evaluation.template_id
        ):
            raise ValidationError(
                "Criterion must belong to the evaluation template."
            )

    def __str__(self):
        return (
            f"{self.evaluation.student} - "
            f"{self.criterion.name}: "
            f"{self.rating}"
        )
