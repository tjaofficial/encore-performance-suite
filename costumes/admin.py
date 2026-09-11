from django.contrib import admin

from .models import (
    Costume,
    CostumeImage,
    CostumeLink,
    StudentCostumeAssignment,
    StudentMeasurementSet,
)


@admin.register(StudentMeasurementSet)
class StudentMeasurementSetAdmin(admin.ModelAdmin):
    list_display = (
        "student",
        "studio",
        "is_complete",
        "measured_at",
        "measured_by",
        "updated_at",
    )

    list_filter = (
        "studio",
        "is_complete",
    )

    search_fields = (
        "student__first_name",
        "student__last_name",
    )


class CostumeImageInline(admin.TabularInline):
    model = CostumeImage
    extra = 0


class CostumeLinkInline(admin.TabularInline):
    model = CostumeLink
    extra = 0


class StudentCostumeAssignmentInline(
    admin.TabularInline
):
    model = StudentCostumeAssignment
    extra = 0


@admin.register(Costume)
class CostumeAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "dance",
        "studio",
        "is_active",
        "updated_at",
    )

    list_filter = (
        "studio",
        "is_active",
    )

    search_fields = (
        "name",
        "dance__title",
        "dance__class_instance__name",
    )

    inlines = [
        CostumeImageInline,
        CostumeLinkInline,
        StudentCostumeAssignmentInline,
    ]


admin.site.register(CostumeImage)
admin.site.register(CostumeLink)
admin.site.register(StudentCostumeAssignment)
