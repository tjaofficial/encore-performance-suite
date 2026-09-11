from django.apps import AppConfig


class CostumesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "costumes"
    verbose_name = "Costumes & Measurements"

    def ready(self):
        from . import signals  # noqa: F401
