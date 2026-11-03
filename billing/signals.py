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


# Queue real newly-created recurring invoices and confirmed payments.
# Never send email inside a database transaction.
from django.db import transaction
from .models import Charge, Payment

@receiver(post_save, sender=Charge)
def queue_new_charge_email(sender, instance, created, raw=False, **kwargs):
    if raw or not created or not instance.recurring_schedule_id:
        return
    from .email_notifications import queue_charge_notice
    transaction.on_commit(lambda pk=instance.pk: queue_charge_notice(pk))

@receiver(post_save, sender=Payment)
def queue_confirmed_payment_email(sender, instance, created, raw=False, **kwargs):
    if raw or not created or instance.status != Payment.Status.SUCCEEDED:
        return
    from .email_notifications import queue_payment_notice
    transaction.on_commit(lambda pk=instance.pk: queue_payment_notice(pk))
