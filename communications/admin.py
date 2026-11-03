from django.contrib import admin

from .models import Announcement, AnnouncementRead


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "studio",
        "audience",
        "priority",
        "is_pinned",
        "is_published",
        "publish_at",
        "expires_at",
    )

    list_filter = (
        "studio",
        "audience",
        "priority",
        "is_pinned",
        "is_published",
    )

    search_fields = (
        "title",
        "message",
    )

    filter_horizontal = (
        "classes",
    )


@admin.register(AnnouncementRead)
class AnnouncementReadAdmin(admin.ModelAdmin):
    list_display = (
        "announcement",
        "user",
        "read_at",
    )

    list_filter = (
        "announcement__studio",
    )


from .models import OutboundEmailLog, OutboundEmailEvent

@admin.register(OutboundEmailLog)
class OutboundEmailLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "studio", "subject", "status", "provider_message_id")
    list_filter = ("studio", "status", "category")
    search_fields = ("subject", "provider_message_id", "sender")
    readonly_fields = [field.name for field in OutboundEmailLog._meta.fields]
    def has_add_permission(self, request):
        return False
    def has_change_permission(self, request, obj=None):
        return False

@admin.register(OutboundEmailEvent)
class OutboundEmailEventAdmin(admin.ModelAdmin):
    list_display = ("occurred_at", "email", "event_type")
    readonly_fields = [field.name for field in OutboundEmailEvent._meta.fields]
    def has_add_permission(self, request):
        return False
    def has_change_permission(self, request, obj=None):
        return False
