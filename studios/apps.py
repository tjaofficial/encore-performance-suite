from django.apps import AppConfig


class StudiosConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "studios"

    def ready(self):
        import studios.signals