from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Studio, StudioSettings


@receiver(post_save, sender=Studio)
def create_studio_settings(sender, instance, created, **kwargs):
    if created:
        StudioSettings.objects.create(studio=instance)