from django.contrib import admin

from .models import CalendarEvent


@admin.register(CalendarEvent)
class CalendarEventAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "studio",
        "event_type",
        "audience",
        "start_at",
        "end_at",
        "is_active",
    )

    list_filter = (
        "studio",
        "event_type",
        "audience",
        "is_active",
    )

    search_fields = (
        "title",
        "description",
        "class_instance__class_id",
        "class_instance__name",
        "instructor__first_name",
        "instructor__last_name",
    )

    autocomplete_fields = (
        "class_instance",
        "instructor",
        "created_by",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    date_hierarchy = "start_at"
