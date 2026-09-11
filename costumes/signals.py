from django.db.models.signals import post_save
from django.dispatch import receiver

from enrollments.models import Enrollment

from .models import Costume
from .services import sync_costume_assignments


@receiver(
    post_save,
    sender=Enrollment,
)
def refresh_costume_assignments_for_enrollment(
    sender,
    instance,
    **kwargs,
):
    costumes = (
        Costume.objects
        .filter(
            dance__class_instance=instance.class_instance,
            is_active=True,
        )
        .select_related(
            "dance",
            "dance__class_instance",
        )
    )

    for costume in costumes:
        sync_costume_assignments(
            costume
        )
