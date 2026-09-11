from django.contrib import admin

from .models import ClassResource


@admin.register(ClassResource)
class ClassResourceAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "studio",
        "class_instance",
        "resource_type",
        "visibility",
        "is_active",
        "created_at",
    )

    list_filter = (
        "studio",
        "resource_type",
        "visibility",
        "is_active",
    )

    search_fields = (
        "title",
        "description",
        "class_instance__name",
        "class_instance__class_id",
    )
