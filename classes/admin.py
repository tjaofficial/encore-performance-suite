from django.contrib import admin

from .models import Class, ClassMeeting, ClassType, Season


class ClassMeetingInline(admin.TabularInline):
    model = ClassMeeting
    extra = 1


@admin.register(Season)
class SeasonAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "studio",
        "start_date",
        "end_date",
        "is_active",
        "registration_open",
    )

    list_filter = (
        "studio",
        "is_active",
        "registration_open",
    )

    search_fields = (
        "name",
        "studio__name",
    )


@admin.register(ClassType)
class ClassTypeAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "studio",
        "is_active",
    )

    list_filter = (
        "studio",
        "is_active",
    )

    search_fields = (
        "name",
        "studio__name",
    )


@admin.register(Class)
class ClassAdmin(admin.ModelAdmin):
    list_display = (
        "class_id",
        "name",
        "studio",
        "season",
        "class_type",
        "instructor",
        "capacity",
        "display_available_slots",
        "is_active",
        "registration_open",
    )

    list_filter = (
        "studio",
        "season",
        "class_type",
        "instructor",
        "is_active",
        "registration_open",
        "allow_drop_ins",
    )

    search_fields = (
        "class_id",
        "name",
        "description",
        "instructor__first_name",
        "instructor__last_name",
    )

    filter_horizontal = (
        "prerequisites",
    )

    inlines = [
        ClassMeetingInline,
    ]

    def display_available_slots(self, obj):
        return obj.available_slots

    display_available_slots.short_description = "Available Slots"


@admin.register(ClassMeeting)
class ClassMeetingAdmin(admin.ModelAdmin):
    list_display = (
        "class_instance",
        "day_of_week",
        "start_time",
        "duration_minutes",
        "location",
        "is_active",
    )

    list_filter = (
        "day_of_week",
        "is_active",
        "class_instance__studio",
        "class_instance__season",
    )

    search_fields = (
        "class_instance__class_id",
        "class_instance__name",
    )
