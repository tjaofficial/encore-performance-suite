from django.contrib import admin

from .models import (
    Task,
    TaskAssignment,
    TaskCompletion,
    TaskNotification,
    TaskTemplate,
    TaskTemplateItem,
    TaskTemplateRun,
    TaskTemplateTrigger,
)


class TaskAssignmentInline(admin.TabularInline):
    model = TaskAssignment
    extra = 0


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "studio",
        "context_type",
        "audience_type",
        "priority",
        "approval_status",
        "due_date",
        "is_active",
    )

    list_filter = (
        "studio",
        "context_type",
        "audience_type",
        "priority",
        "approval_status",
        "is_active",
    )

    search_fields = (
        "title",
        "description",
        "class_instance__name",
        "student__first_name",
        "student__last_name",
    )

    inlines = [
        TaskAssignmentInline,
    ]


@admin.register(TaskAssignment)
class TaskAssignmentAdmin(admin.ModelAdmin):
    list_display = (
        "task",
        "recipient_type",
        "user",
        "student",
        "completed_at",
    )


@admin.register(TaskCompletion)
class TaskCompletionAdmin(admin.ModelAdmin):
    list_display = (
        "task",
        "user",
        "completed_at",
    )


@admin.register(TaskNotification)
class TaskNotificationAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "studio",
        "user",
        "kind",
        "created_at",
        "read_at",
    )


class TaskTemplateItemInline(admin.TabularInline):
    model = TaskTemplateItem
    extra = 0


class TaskTemplateTriggerInline(admin.TabularInline):
    model = TaskTemplateTrigger
    extra = 0


@admin.register(TaskTemplate)
class TaskTemplateAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "studio",
        "created_by",
        "visibility",
        "status",
    )

    inlines = [
        TaskTemplateItemInline,
        TaskTemplateTriggerInline,
    ]


@admin.register(TaskTemplateRun)
class TaskTemplateRunAdmin(admin.ModelAdmin):
    list_display = (
        "template",
        "status",
        "target_label",
        "tasks_created_count",
        "started_at",
        "completed_at",
    )

    readonly_fields = (
        "idempotency_key",
        "error_message",
    )
