from django.contrib import admin

from .models import Instructor, InstructorAvailability


class InstructorAvailabilityInline(admin.TabularInline):
    model = InstructorAvailability
    extra = 1


@admin.register(Instructor)
class InstructorAdmin(admin.ModelAdmin):
    list_display = (
        "first_name",
        "last_name",
        "email",
        "phone",
        "studio",
        "is_active",
    )

    list_filter = (
        "studio",
        "is_active",
    )

    search_fields = (
        "first_name",
        "last_name",
        "email",
        "phone",
    )

    inlines = [
        InstructorAvailabilityInline,
    ]


@admin.register(InstructorAvailability)
class InstructorAvailabilityAdmin(admin.ModelAdmin):
    list_display = (
        "instructor",
        "day_of_week",
        "start_time",
        "end_time",
        "is_available",
    )

    list_filter = (
        "day_of_week",
        "is_available",
        "instructor__studio",
    )

    search_fields = (
        "instructor__first_name",
        "instructor__last_name",
    )
