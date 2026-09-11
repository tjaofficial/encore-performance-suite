from django.db.models.signals import post_save
from django.dispatch import receiver

from enrollments.models import Enrollment
from families.models import Family

from .models import FamilyAccount
from .services import sync_billing_for_enrollment


@receiver(post_save, sender=Family)
def ensure_family_billing_account(
    sender,
    instance,
    created,
    **kwargs,
):
    if kwargs.get("raw"):
        return

    FamilyAccount.objects.get_or_create(
        family=instance,
        defaults={
            "studio": instance.studio,
        },
    )


@receiver(post_save, sender=Enrollment)
def sync_enrollment_billing(
    sender,
    instance,
    **kwargs,
):
    if kwargs.get("raw"):
        return

    sync_billing_for_enrollment(instance)
