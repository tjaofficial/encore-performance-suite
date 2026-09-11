from django.db import transaction

from enrollments.models import Enrollment

from .models import AttendanceRecord, AttendanceSession


@transaction.atomic
def create_attendance_session_with_roster(
    *,
    class_instance,
    session_date,
    taken_by=None,
    start_time=None,
):
    """
    Create an attendance session and pre-populate all actively enrolled
    students as Present.

    Teachers can then change only the students who were absent/late/etc.
    """
    session, created = AttendanceSession.objects.get_or_create(
        class_instance=class_instance,
        session_date=session_date,
        start_time=start_time,
        defaults={
            "taken_by": taken_by,
        },
    )

    if not created:
        return session, False

    active_enrollments = (
        Enrollment.objects
        .filter(
            class_instance=class_instance,
            status=Enrollment.Status.ACTIVE,
        )
        .select_related("student")
    )

    AttendanceRecord.objects.bulk_create(
        [
            AttendanceRecord(
                session=session,
                student=enrollment.student,
                status=AttendanceRecord.Status.PRESENT,
                marked_by=taken_by,
            )
            for enrollment in active_enrollments
        ]
    )

    return session, True
