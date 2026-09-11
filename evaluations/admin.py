from django.contrib import admin

from .models import (
    EvaluationCriterion,
    EvaluationRating,
    EvaluationTemplate,
    StudentEvaluation,
)


class EvaluationCriterionInline(admin.TabularInline):
    model = EvaluationCriterion
    extra = 1


@admin.register(EvaluationTemplate)
class EvaluationTemplateAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "studio",
        "class_type",
        "is_active",
    )

    list_filter = (
        "studio",
        "is_active",
    )

    inlines = [
        EvaluationCriterionInline,
    ]


class EvaluationRatingInline(admin.TabularInline):
    model = EvaluationRating
    extra = 0


@admin.register(StudentEvaluation)
class StudentEvaluationAdmin(admin.ModelAdmin):
    list_display = (
        "student",
        "class_instance",
        "instructor",
        "evaluation_date",
        "status",
    )

    list_filter = (
        "studio",
        "status",
        "evaluation_date",
    )

    inlines = [
        EvaluationRatingInline,
    ]


admin.site.register(EvaluationCriterion)
admin.site.register(EvaluationRating)
