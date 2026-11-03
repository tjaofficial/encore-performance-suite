from django.contrib import admin

from .models import (
    Studio,
    StudioLocation,
    StudioMembership,
    StudioSettings,
)


class StudioLocationInline(admin.TabularInline):
    model = StudioLocation
    extra = 0


class StudioMembershipInline(admin.TabularInline):
    model = StudioMembership
    extra = 0


@admin.register(Studio)
class StudioAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "slug",
        "email",
        "timezone",
        "is_active",
    )

    search_fields = (
        "name",
        "slug",
        "email",
    )

    list_filter = (
        "is_active",
        "timezone",
    )

    prepopulated_fields = {
        "slug": ("name",),
    }

    inlines = [
        StudioLocationInline,
        StudioMembershipInline,
    ]


@admin.register(StudioMembership)
class StudioMembershipAdmin(admin.ModelAdmin):
    # Studio access is controlled by membership, independently of the
    # instructor profile linked to a user account.
    list_display = (
        "user",
        "user_email",
        "studio",
        "role",
        "is_active",
        "joined_at",
    )
    list_display_links = ("user",)
    list_editable = ("is_active",)
    list_select_related = ("user", "studio")
    list_filter = (
        "studio",
        "role",
        "is_active",
    )
    search_fields = (
        "=user__id",
        "user__username",
        "user__email",
        "user__first_name",
        "user__last_name",
        "studio__name",
        "studio__slug",
    )
    ordering = ("studio__name", "user__username", "role")
    raw_id_fields = ("user",)
    readonly_fields = ("joined_at",)
    fieldsets = (
        ("Access", {"fields": ("studio", "user", "role", "is_active")}),
        ("Onboarding tour", {
            "fields": ("onboarding_tour_status", "onboarding_tour_step"),
            "classes": ("collapse",),
        }),
        ("Record", {"fields": ("joined_at",)}),
    )

    @admin.display(description="Email", ordering="user__email")
    def user_email(self, obj):
        return obj.user.email or "—"


@admin.register(StudioLocation)
class StudioLocationAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "studio",
        "city",
        "state",
        "is_primary",
        "is_active",
    )

    list_filter = (
        "is_primary",
        "is_active",
        "state",
    )


@admin.register(StudioSettings)
class StudioSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "studio",
        "allow_online_registration",
        "evaluation_enabled",
        "dashboard_customization_enabled",
    )