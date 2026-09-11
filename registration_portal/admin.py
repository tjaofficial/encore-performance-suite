from django.contrib import admin

from .models import (
    FamilyInvite,
    RegistrationRequest,
)


@admin.register(RegistrationRequest)
class RegistrationRequestAdmin(admin.ModelAdmin):
    list_display = (
        "student_first_name",
        "student_last_name",
        "studio",
        "class_instance",
        "email",
        "status",
        "created_at",
    )

    list_filter = (
        "studio",
        "status",
        "class_instance__season",
    )

    search_fields = (
        "guardian_first_name",
        "guardian_last_name",
        "student_first_name",
        "student_last_name",
        "email",
        "phone",
    )


@admin.register(FamilyInvite)
class FamilyInviteAdmin(admin.ModelAdmin):
    list_display = (
        "email",
        "studio",
        "family",
        "created_at",
        "expires_at",
        "accepted_at",
    )

    list_filter = (
        "studio",
        "created_at",
        "accepted_at",
    )

    search_fields = (
        "email",
        "guardian_first_name",
        "guardian_last_name",
    )

    readonly_fields = (
        "token",
        "created_at",
        "accepted_at",
    )
