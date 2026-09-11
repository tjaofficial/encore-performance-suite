from django.db.models.signals import post_save
from django.dispatch import receiver

from classes.models import Class
from enrollments.models import Enrollment
from instructors.models import Instructor
from students.models import Student

from .models import TaskTemplateTrigger
from .services import run_event_templates


@receiver(post_save, sender=Class)
def task_templates_new_class(
    sender,
    instance,
    created,
    **kwargs,
):
    if not created:
        return

    run_event_templates(
        instance.studio,
        TaskTemplateTrigger.TriggerType.NEW_CLASS,
        instance,
    )


@receiver(post_save, sender=Student)
def task_templates_new_student(
    sender,
    instance,
    created,
    **kwargs,
):
    if not created:
        return

    run_event_templates(
        instance.studio,
        TaskTemplateTrigger.TriggerType.NEW_STUDENT,
        instance,
    )


@receiver(post_save, sender=Instructor)
def task_templates_new_instructor(
    sender,
    instance,
    created,
    **kwargs,
):
    if not created:
        return

    run_event_templates(
        instance.studio,
        TaskTemplateTrigger.TriggerType.NEW_INSTRUCTOR,
        instance,
    )


@receiver(post_save, sender=Enrollment)
def task_templates_new_enrollment(
    sender,
    instance,
    created,
    **kwargs,
):
    if not created:
        return

    run_event_templates(
        instance.class_instance.studio,
        TaskTemplateTrigger.TriggerType.NEW_ENROLLMENT,
        instance,
    )
