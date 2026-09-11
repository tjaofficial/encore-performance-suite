from django.contrib import admin

from .models import Family, Guardian


class GuardianInline(admin.TabularInline):
    model = Guardian
    extra = 0


@admin.register(Family)
class FamilyAdmin(admin.ModelAdmin):
    list_display = (
        "family_name",
        "primary_contact_first_name",
        "primary_contact_last_name",
        "primary_email",
        "primary_phone",
        "studio",
        "is_active",
    )

    list_filter = (
        "studio",
        "is_active",
    )

    search_fields = (
        "family_name",
        "primary_contact_first_name",
        "primary_contact_last_name",
        "primary_email",
        "primary_phone",
    )

    inlines = [
        GuardianInline,
    ]


@admin.register(Guardian)
class GuardianAdmin(admin.ModelAdmin):
    list_display = (
        "first_name",
        "last_name",
        "family",
        "relationship",
        "email",
        "is_primary",
        "is_active",
    )

    list_filter = (
        "is_primary",
        "is_active",
        "family__studio",
    )

    search_fields = (
        "first_name",
        "last_name",
        "email",
        "phone",
    )