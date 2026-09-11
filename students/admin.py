from django.contrib import admin

from .models import Student


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = (
        "first_name",
        "last_name",
        "birthday",
        "display_age",
        "studio",
        "family",
        "performing",
        "is_active",
        "enrollment_blocked",
    )

    list_filter = (
        "studio",
        "is_active",
        "performing",
        "enrollment_blocked",
        "gender",
    )

    search_fields = (
        "first_name",
        "last_name",
        "family__family_name",
        "family__primary_email",
    )

    readonly_fields = (
        "display_age",
    )

    def display_age(self, obj):
        return obj.age

    display_age.short_description = "Age"