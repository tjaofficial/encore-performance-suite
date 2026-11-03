from django.db.models import Count, Q
from django.utils import timezone

from communications.models import Announcement, WorkspaceNotification
from enrollments.models import Enrollment
from families.models import Guardian
from students.models import Student


def parent_portal_context(
    request,
    studio,
    *,
    selected_student=None,
    section="dashboard",
):
    guardian = (
        Guardian.objects
        .filter(
            family__studio=studio,
            user=request.user,
            is_active=True,
        )
        .select_related("family")
        .order_by("-is_primary", "pk")
        .first()
    )

    if guardian is None:
        return {}

    family = guardian.family

    students = list(
        Student.objects
        .filter(
            studio=studio,
            family=family,
            is_active=True,
        )
        .annotate(
            active_class_count=Count(
                "enrollments",
                filter=Q(
                    enrollments__status=Enrollment.Status.ACTIVE,
                ),
                distinct=True,
            )
        )
        .order_by("first_name", "last_name")
    )

    if selected_student is not None:
        selected_student = next(
            (
                item
                for item in students
                if item.pk == selected_student.pk
            ),
            None,
        )

    requested_student = str(
        request.GET.get("student", "") or ""
    ).strip()

    if selected_student is None and requested_student.isdigit():
        selected_student = next(
            (
                item
                for item in students
                if item.pk == int(requested_student)
            ),
            None,
        )

    if selected_student is None and students:
        selected_student = students[0]

    dancer_rows = [
        {
            "student": student,
            "class_count": student.active_class_count,
            "is_selected": (
                selected_student is not None
                and selected_student.pk == student.pk
            ),
        }
        for student in students
    ]

    active_class_ids = list(
        Enrollment.objects
        .filter(
            student__family=family,
            student__is_active=True,
            status=Enrollment.Status.ACTIVE,
            class_instance__studio=studio,
        )
        .values_list("class_instance_id", flat=True)
        .distinct()
    )

    now = timezone.now()
    visible_announcements = (
        Announcement.objects
        .filter(
            studio=studio,
            is_published=True,
            publish_at__lte=now,
        )
        .filter(
            Q(expires_at__isnull=True)
            | Q(expires_at__gt=now)
        )
        .filter(
            Q(
                audience__in=[
                    Announcement.Audience.STUDIO,
                    Announcement.Audience.FAMILIES,
                ]
            )
            | Q(
                audience=Announcement.Audience.CLASS,
                classes__id__in=active_class_ids,
            )
        )
        .distinct()
    )

    unread_notifications = WorkspaceNotification.objects.filter(
        studio=studio, user=request.user, read_at__isnull=True,
    ).order_by("-created_at", "-pk")
    unread_notification_count = unread_notifications.count()
    notification_preview = list(unread_notifications[:5])

    return {
        "guardian": guardian,
        "family": family,
        "dancer_rows": dancer_rows,
        "selected_student": selected_student,
        "parent_section": section,
        "parent_unread_notification_count": unread_notification_count,
        "parent_notification_preview": notification_preview,
    }
