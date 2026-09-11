from django.contrib import admin

from .models import ExtraWorkEntry


@admin.register(ExtraWorkEntry)
class ExtraWorkEntryAdmin(admin.ModelAdmin):
    list_display = (
        "work_date",
        "user",
        "studio",
        "category",
        "duration_minutes",
    )

    list_filter = (
        "studio",
        "category",
        "work_date",
    )

    search_fields = (
        "user__first_name",
        "user__last_name",
        "user__email",
        "description",
    )
