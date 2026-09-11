from django.contrib import admin

from .models import Enrollment


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = (
        "student",
        "class_instance",
        "status",
        "source",
        "display_tuition",
        "enrolled_at",
    )

    list_filter = (
        "status",
        "source",
        "class_instance__studio",
        "class_instance__season",
        "class_instance__class_type",
    )

    search_fields = (
        "student__first_name",
        "student__last_name",
        "class_instance__class_id",
        "class_instance__name",
    )

    autocomplete_fields = (
        "student",
        "class_instance",
    )

    readonly_fields = (
        "enrolled_at",
        "created_at",
        "updated_at",
        "display_tuition",
    )

    def display_tuition(self, obj):
        return obj.tuition_amount

    display_tuition.short_description = "Tuition"
