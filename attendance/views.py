from datetime import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from classes.models import Class
from families.models import Guardian
from instructors.models import Instructor
from students.models import Student
from studios.models import Studio

from .models import AttendanceRecord, AttendanceSession
from .services import create_attendance_session_with_roster


def _get_teacher_for_class(user, studio, class_instance):
    if user.is_superuser:
        return class_instance.instructor

    instructor = (
        Instructor.objects
        .filter(
            studio=studio,
            user=user,
            is_active=True,
        )
        .first()
    )

    if not instructor:
        return None

    if (
        class_instance.instructor_id != instructor.id
        and class_instance.assistant_instructor_id != instructor.id
    ):
        return None

    return instructor


@login_required
def take_attendance(request, studio_slug, class_id):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    class_instance = get_object_or_404(
        Class.objects.select_related(
            "instructor",
            "assistant_instructor",
            "season",
        ),
        pk=class_id,
        studio=studio,
        is_active=True,
    )

    instructor = _get_teacher_for_class(
        request.user,
        studio,
        class_instance,
    )

    if instructor is None:
        raise Http404

    session_date_raw = request.GET.get("date")
    start_time_raw = request.GET.get("start")

    session_date = timezone.localdate()

    if session_date_raw:
        try:
            session_date = datetime.strptime(
                session_date_raw,
                "%Y-%m-%d",
            ).date()
        except ValueError:
            pass

    start_time = None

    if start_time_raw:
        try:
            start_time = datetime.strptime(
                start_time_raw,
                "%H:%M:%S",
            ).time()
        except ValueError:
            try:
                start_time = datetime.strptime(
                    start_time_raw,
                    "%H:%M",
                ).time()
            except ValueError:
                start_time = None

    session, _ = create_attendance_session_with_roster(
        class_instance=class_instance,
        session_date=session_date,
        start_time=start_time,
        taken_by=request.user,
    )

    records = (
        session.records
        .select_related("student")
        .order_by(
            "student__last_name",
            "student__first_name",
        )
    )

    return render(
        request,
        "attendance/take_attendance.html",
        {
            "studio": studio,
            "role": "teacher",
            "class_instance": class_instance,
            "session": session,
            "records": records,
        },
    )


@login_required
@transaction.atomic
def update_attendance(request, studio_slug, session_id):
    if request.method != "POST":
        raise Http404

    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    session = get_object_or_404(
        AttendanceSession.objects.select_related(
            "class_instance",
            "class_instance__instructor",
            "class_instance__assistant_instructor",
        ),
        pk=session_id,
        class_instance__studio=studio,
    )

    instructor = _get_teacher_for_class(
        request.user,
        studio,
        session.class_instance,
    )

    if instructor is None:
        raise Http404

    valid_statuses = {
        choice[0]
        for choice in AttendanceRecord.Status.choices
    }

    for record in session.records.select_related("student"):
        status = request.POST.get(
            f"status_{record.pk}",
            record.status,
        )

        if status not in valid_statuses:
            continue

        note = request.POST.get(
            f"note_{record.pk}",
            "",
        ).strip()

        record.status = status
        record.note = note
        record.marked_by = request.user
        record.save(
            update_fields=[
                "status",
                "note",
                "marked_by",
                "marked_at",
            ]
        )

    if "finalize" in request.POST:
        session.is_finalized = True
        session.taken_by = request.user
        session.save(
            update_fields=[
                "is_finalized",
                "taken_by",
                "updated_at",
            ]
        )
        messages.success(
            request,
            "Attendance finalized.",
        )
    else:
        messages.success(
            request,
            "Attendance saved.",
        )

    return redirect(
        "attendance:take_attendance",
        studio_slug=studio.slug,
        class_id=session.class_instance_id,
    )


def _attendance_history_context(student, studio, role):
    records = (
        AttendanceRecord.objects
        .filter(
            student=student,
            session__class_instance__studio=studio,
        )
        .select_related(
            "session",
            "session__class_instance",
            "session__class_instance__instructor",
        )
        .order_by("-session__session_date")
    )

    class_id = None

    total = records.count()

    present_like = records.filter(
        status__in=[
            AttendanceRecord.Status.PRESENT,
            AttendanceRecord.Status.LATE,
            AttendanceRecord.Status.LEFT_EARLY,
        ]
    ).count()

    absent = records.filter(
        status=AttendanceRecord.Status.ABSENT,
    ).count()

    excused = records.filter(
        status=AttendanceRecord.Status.EXCUSED,
    ).count()

    late = records.filter(
        status=AttendanceRecord.Status.LATE,
    ).count()

    percentage = (
        round((present_like / total) * 100)
        if total
        else None
    )

    return {
        "studio": studio,
        "role": role,
        "student": student,
        "records": records,
        "total": total,
        "present_like": present_like,
        "absent": absent,
        "excused": excused,
        "late": late,
        "percentage": percentage,
    }


@login_required
def student_attendance_history(request, studio_slug):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    student = (
        Student.objects
        .filter(
            studio=studio,
            user=request.user,
            is_active=True,
        )
        .first()
    )

    if not student:
        raise Http404

    return render(
        request,
        "attendance/history.html",
        _attendance_history_context(
            student,
            studio,
            "student",
        ),
    )


@login_required
def family_student_attendance_history(
    request,
    studio_slug,
    student_id,
):
    studio = get_object_or_404(
        Studio,
        slug=studio_slug,
        is_active=True,
    )

    guardian = (
        Guardian.objects
        .filter(
            family__studio=studio,
            user=request.user,
            is_active=True,
        )
        .select_related("family")
        .first()
    )

    if not guardian:
        raise Http404

    student = get_object_or_404(
        Student,
        pk=student_id,
        family=guardian.family,
        studio=studio,
    )

    return render(
        request,
        "attendance/history.html",
        _attendance_history_context(
            student,
            studio,
            "family",
        ),
    )
