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
