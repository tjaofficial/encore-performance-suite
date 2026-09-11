from django.contrib import admin

from .models import AttendanceRecord, AttendanceSession


class AttendanceRecordInline(admin.TabularInline):
    model = AttendanceRecord
    extra = 0

    fields = (
        "student",
        "status",
        "arrival_time",
        "departure_time",
        "note",
        "marked_by",
    )

    autocomplete_fields = (
        "student",
        "marked_by",
    )


@admin.register(AttendanceSession)
class AttendanceSessionAdmin(admin.ModelAdmin):
    list_display = (
        "class_instance",
        "session_date",
        "start_time",
        "taken_by",
        "is_finalized",
    )

    list_filter = (
        "is_finalized",
        "session_date",
        "class_instance__studio",
        "class_instance__season",
        "class_instance__class_type",
    )

    search_fields = (
        "class_instance__class_id",
        "class_instance__name",
        "taken_by__email",
    )

    autocomplete_fields = (
        "class_instance",
        "taken_by",
    )

    inlines = [
        AttendanceRecordInline,
    ]

    date_hierarchy = "session_date"


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = (
        "student",
        "class_name",
        "session_date",
        "status",
        "arrival_time",
        "departure_time",
        "marked_by",
    )

    list_filter = (
        "status",
        "session__session_date",
        "session__class_instance__studio",
        "session__class_instance__season",
    )

    search_fields = (
        "student__first_name",
        "student__last_name",
        "session__class_instance__class_id",
        "session__class_instance__name",
    )

    autocomplete_fields = (
        "student",
        "session",
        "marked_by",
    )

    def class_name(self, obj):
        return obj.session.class_instance.name

    class_name.short_description = "Class"

    def session_date(self, obj):
        return obj.session.session_date

    session_date.short_description = "Date"
