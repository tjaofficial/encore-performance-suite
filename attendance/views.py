from calendar import monthrange
from collections import defaultdict
from datetime import date, datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import models, transaction
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from classes.models import Class, ClassMeeting, Season
from communications.models import EmailTemplate
from dashboard.parent_portal import parent_portal_context
from enrollments.models import Enrollment
from families.models import Guardian
from instructors.models import Instructor
from students.models import Student
from studios.models import Studio

from .models import (
    AbsenceRequest,
    AttendanceAutomationTrigger,
    AttendancePolicy,
    MakeupEligibilityRule,
    AttendanceRecord,
    AttendanceSession,
    MakeupAssignment,
    MakeupRequirement,
)
from .makeup_task_services import sync_makeup_tasks

from .services import (
    add_makeup_student_to_session,
    create_attendance_session_with_roster,
    outstanding_makeup_count,
    prior_consecutive_absence_count,
    process_finalized_makeup_record,
    process_finalized_regular_absence,
    warning_threshold_for_studio,
    eligible_makeup_dates,
    validate_makeup_booking,
)


STATUS_SHORT = {
    AttendanceRecord.Status.PRESENT: "P",
    AttendanceRecord.Status.ABSENT: "A",
    AttendanceRecord.Status.LATE: "L",
    AttendanceRecord.Status.EXCUSED: "E",
    AttendanceRecord.Status.LEFT_EARLY: "LE",
}


def _is_studio_admin(user, studio):
    if user.is_superuser:
        return True

    return user.studio_memberships.filter(
        studio=studio,
        role="administrator",
        is_active=True,
    ).exists()


def _get_teacher_for_class(user, studio, class_instance):
    if _is_studio_admin(user, studio):
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


def _teacher_class_ids(user, studio):
    if _is_studio_admin(user, studio):
        return list(
            Class.objects.filter(
                studio=studio,
                is_active=True,
            ).values_list("id", flat=True)
        )

    instructor = Instructor.objects.filter(
        studio=studio,
        user=user,
        is_active=True,
    ).first()
    if not instructor:
        return []

    ids = set(
        instructor.primary_classes.filter(
            studio=studio,
            is_active=True,
        ).values_list("id", flat=True)
    )
    ids.update(
        instructor.assistant_classes.filter(
            studio=studio,
            is_active=True,
        ).values_list("id", flat=True)
    )
    return list(ids)


def _month_anchor(raw_value=None):
    if raw_value:
        try:
            return datetime.strptime(raw_value, "%Y-%m").date().replace(day=1)
        except ValueError:
            pass
    return timezone.localdate().replace(day=1)


def _month_bounds(anchor):
    last_day = monthrange(anchor.year, anchor.month)[1]
    return anchor, anchor.replace(day=last_day)


def _month_label(anchor):
    return anchor.strftime("%B %Y")


def _allowed_class_or_404(studio, class_id, class_ids):
    class_instance = get_object_or_404(
        Class.objects.select_related("season", "instructor", "assistant_instructor"),
        pk=class_id,
        studio=studio,
        is_active=True,
    )
    if class_instance.id not in class_ids and not class_instance.studio_id == studio.id:
        raise Http404
    return class_instance


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

    records = list(
        session.records
        .filter(context=AttendanceRecord.Context.REGULAR)
        .select_related("student")
        .order_by("student__last_name", "student__first_name")
    )
    makeup_records = list(
        session.records
        .filter(context=AttendanceRecord.Context.MAKEUP)
        .select_related(
            "student",
            "makeup_assignment",
            "makeup_assignment__source_class",
            "makeup_assignment__requirement",
        )
        .order_by("student__last_name", "student__first_name")
    )
    warning_threshold = warning_threshold_for_studio(studio)
    for record in records:
        record.prior_consecutive_absences = prior_consecutive_absence_count(
            record.student,
            class_instance,
            before_session=session,
        )

    return render(
        request,
        "attendance/take_attendance.html",
        {
            "studio": studio,
            "role": (
                "administrator"
                if _is_studio_admin(request.user, studio)
                else "teacher"
            ),
            "class_instance": class_instance,
            "session": session,
            "records": records,
            "makeup_records": makeup_records,
            "warning_threshold": warning_threshold,
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
        for record in session.records.select_related(
            "student",
            "student__user",
            "student__family",
            "makeup_assignment",
            "makeup_assignment__requirement",
            "session__class_instance",
            "session__class_instance__studio",
            "session__class_instance__instructor__user",
            "session__class_instance__assistant_instructor__user",
        ):
            if record.context == AttendanceRecord.Context.MAKEUP:
                process_finalized_makeup_record(record)
            else:
                process_finalized_regular_absence(record, finalized_by=request.user)
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


@login_required
def attendance_manager(request, studio_slug):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    is_admin = _is_studio_admin(request.user, studio)
    class_ids = _teacher_class_ids(request.user, studio)
    if not class_ids and not is_admin:
        raise Http404

    eligible_classes = (
        Class.objects
        .filter(studio=studio, id__in=class_ids, is_active=True)
        .select_related("season", "instructor")
        .order_by("name")
    )
    available_seasons = (
        Season.objects
        .filter(studio=studio, classes__id__in=class_ids)
        .distinct()
        .order_by("-start_date", "name")
    )
    policy, _ = AttendancePolicy.objects.get_or_create(studio=studio)
    can_assign_makeups = is_admin or (
        policy.teachers_can_assign_makeups and bool(class_ids)
    )

    if request.method == "POST":
        action = request.POST.get("action", "")
        if action != "schedule_makeup":
            raise Http404
        if not can_assign_makeups:
            raise Http404
        if action == "schedule_makeup":
            requirement = get_object_or_404(
                MakeupRequirement.objects.select_related("student", "source_class"),
                pk=request.POST.get("requirement_id"),
                source_class__studio=studio,
                source_class_id__in=class_ids,
                status=MakeupRequirement.Status.OUTSTANDING,
            )
            meeting = get_object_or_404(
                ClassMeeting.objects.select_related("class_instance", "class_instance__season"),
                pk=request.POST.get("meeting_id"),
                class_instance__studio=studio,
            )
            date_string = request.POST.get("scheduled_date", "")
            try:
                booked_date = date.fromisoformat(date_string)
                validate_makeup_booking(
                    source_class=requirement.source_class,
                    meeting=meeting,
                    booked_date=booked_date,
                )
                if MakeupAssignment.objects.filter(
                    requirement=requirement,
                    status__in=[MakeupAssignment.Status.SCHEDULED, MakeupAssignment.Status.COMPLETED],
                ).exists():
                    raise ValueError("This requirement already has a scheduled or completed make-up.")
                if MakeupAssignment.objects.filter(
                    student=requirement.student,
                    scheduled_date=booked_date,
                    status__in=[MakeupAssignment.Status.SCHEDULED, MakeupAssignment.Status.COMPLETED],
                ).exists():
                    raise ValueError("The student already has a make-up booked on this day. Choose another day.")
                MakeupAssignment.objects.create(
                    requirement=requirement,
                    student=requirement.student,
                    source_class=requirement.source_class,
                    makeup_class=meeting.class_instance,
                    makeup_meeting=meeting,
                    scheduled_date=booked_date,
                    added_by=request.user,
                    is_walk_in=False,
                )
                sync_makeup_tasks(requirement.student)
                messages.success(request, "Make-up session assigned.")
            except (ValueError, TypeError) as exc:
                messages.error(request, str(exc) or "Select an available make-up date.")

        return redirect(reverse("attendance:manager", kwargs={"studio_slug": studio.slug}) + "?tab=makeups")

    active_tab = request.GET.get("tab", "submissions")
    if active_tab not in {"submissions", "absences", "makeups", "requests"}:
        active_tab = "submissions"

    submission_season_id = request.GET.get("season") or ""
    submission_class_id = request.GET.get("class") or ""
    submission_status = request.GET.get("status") or ""
    submission_search = request.GET.get("search", "").strip()

    sessions_qs = (
        AttendanceSession.objects
        .filter(class_instance__studio=studio, class_instance_id__in=class_ids)
        .select_related(
            "class_instance",
            "class_instance__season",
            "class_instance__instructor",
            "taken_by",
        )
    )
    if submission_season_id:
        sessions_qs = sessions_qs.filter(class_instance__season_id=submission_season_id)
    if submission_class_id:
        sessions_qs = sessions_qs.filter(class_instance_id=submission_class_id)
    if submission_status == "finalized":
        sessions_qs = sessions_qs.filter(is_finalized=True)
    elif submission_status == "in_progress":
        sessions_qs = sessions_qs.filter(is_finalized=False)
    if submission_search:
        sessions_qs = sessions_qs.filter(
            models.Q(class_instance__name__icontains=submission_search)
            | models.Q(class_instance__class_id__icontains=submission_search)
            | models.Q(class_instance__season__name__icontains=submission_search)
        )
    sessions = list(sessions_qs.order_by("-session_date", "-created_at")[:150])

    absence_student_search = request.GET.get("student", "").strip()
    absence_class_id = request.GET.get("absence_class") or ""
    absence_season_id = request.GET.get("absence_season") or ""
    absence_month_anchor = _month_anchor(request.GET.get("absence_month") or None)
    absence_month_start, absence_month_end = _month_bounds(absence_month_anchor)

    absence_records_qs = (
        AttendanceRecord.objects
        .filter(
            session__class_instance__studio=studio,
            session__class_instance_id__in=class_ids,
            context=AttendanceRecord.Context.REGULAR,
            status=AttendanceRecord.Status.ABSENT,
        )
        .select_related(
            "student",
            "session",
            "session__class_instance",
            "session__class_instance__season",
        )
    )
    if absence_class_id:
        absence_records_qs = absence_records_qs.filter(session__class_instance_id=absence_class_id)
    if absence_season_id:
        absence_records_qs = absence_records_qs.filter(session__class_instance__season_id=absence_season_id)
    if absence_student_search:
        absence_records_qs = absence_records_qs.filter(
            models.Q(student__first_name__icontains=absence_student_search)
            | models.Q(student__last_name__icontains=absence_student_search)
        )
    absence_records_qs = absence_records_qs.filter(
        session__session_date__gte=absence_month_start,
        session__session_date__lte=absence_month_end,
    )
    absence_records = list(
        absence_records_qs.order_by(
            "student__last_name",
            "student__first_name",
            "-session__session_date",
        )
    )

    makeup_counts = {
        (item["student"], item["source_class"]): item["total"]
        for item in (
            MakeupRequirement.objects
            .filter(
                student_id__in={record.student_id for record in absence_records},
                source_class_id__in={record.session.class_instance_id for record in absence_records},
                status=MakeupRequirement.Status.OUTSTANDING,
            )
            .values("student", "source_class")
            .annotate(total=models.Count("id"))
        )
    }

    absence_rows = []
    grouped_absence_records = defaultdict(list)
    for record in absence_records:
        grouped_absence_records[
            (record.student_id, record.session.class_instance_id)
        ].append(record)

    for (student_id, class_id), records in grouped_absence_records.items():
        student = records[0].student
        class_instance = records[0].session.class_instance
        absence_rows.append(
            {
                "student": student,
                "class_instance": class_instance,
                "total_absences": len(records),
                "makeups_owed": makeup_counts.get((student_id, class_id), 0),
            }
        )

    outstanding_makeups = list(
        MakeupRequirement.objects
        .filter(
            source_class__studio=studio,
            source_class_id__in=class_ids,
            status=MakeupRequirement.Status.OUTSTANDING,
        )
        .select_related("student", "source_class", "source_attendance_record__session")
        .order_by("student__last_name", "student__first_name", "created_at")
    )

    # Requirements are created automatically by attendance finalization.
    unassigned_absences = []

    meeting_choices = list(
        MakeupEligibilityRule.objects.filter(
            studio=studio, is_active=True, source_class_id__in=class_ids,
            eligible_meeting__is_active=True,
            eligible_meeting__class_instance__is_active=True,
        ).select_related("source_class", "eligible_meeting", "eligible_meeting__class_instance")
    )
    meeting_choices_by_source = {}
    for rule in meeting_choices:
        meeting_choices_by_source.setdefault(rule.source_class_id, []).append(rule)
    for requirement in outstanding_makeups:
        requirement.available_meetings = meeting_choices_by_source.get(requirement.source_class_id, [])
        requirement.current_booking = (MakeupAssignment.objects.filter(
            requirement=requirement, status=MakeupAssignment.Status.SCHEDULED,
        ).select_related("makeup_class").order_by("scheduled_date").first())

    context = {
        "studio": studio,
        "role": "administrator" if is_admin else "teacher",
        "is_admin": is_admin,
        "active_tab": active_tab,
        "pending_absence_requests": (AbsenceRequest.objects.filter(studio=studio, status="pending")
            .prefetch_related("sessions__student", "sessions__class_instance")
            .order_by("created_at") if is_admin else AbsenceRequest.objects.none()),
        "eligible_classes": eligible_classes,
        "available_seasons": available_seasons,
        "can_assign_makeups": can_assign_makeups,
        "unassigned_absences": unassigned_absences,
        "sessions": sessions,
        "absence_rows": absence_rows,
        "outstanding_makeups": outstanding_makeups,
        "finalized_count": AttendanceSession.objects.filter(class_instance__studio=studio, class_instance_id__in=class_ids, is_finalized=True).count(),
        "in_progress_count": AttendanceSession.objects.filter(class_instance__studio=studio, class_instance_id__in=class_ids, is_finalized=False).count(),
        "absence_count": AttendanceRecord.objects.filter(session__class_instance__studio=studio, session__class_instance_id__in=class_ids, status=AttendanceRecord.Status.ABSENT).count(),
        "makeup_count": len(outstanding_makeups),
        "today": timezone.localdate(),
        "submission_filters": {
            "season": submission_season_id,
            "class": submission_class_id,
            "status": submission_status,
            "search": submission_search,
        },
        "absence_filters": {
            "student": absence_student_search,
            "class": absence_class_id,
            "season": absence_season_id,
            "month": absence_month_anchor.strftime("%Y-%m"),
            "month_label": _month_label(absence_month_anchor),
        },
    }
    return render(request, "attendance/manager.html", context)


@login_required
def attendance_submission_detail(request, studio_slug, class_id):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    class_ids = _teacher_class_ids(request.user, studio)
    if not class_ids and not _is_studio_admin(request.user, studio):
        raise Http404

    class_instance = get_object_or_404(
        Class.objects.select_related("season", "instructor", "assistant_instructor"),
        pk=class_id,
        studio=studio,
        is_active=True,
    )
    if class_instance.id not in class_ids and not _is_studio_admin(request.user, studio):
        raise Http404

    month_anchor = _month_anchor(request.GET.get("month"))
    month_start, month_end = _month_bounds(month_anchor)
    previous_month = (month_anchor.replace(day=1) - timedelta(days=1)).replace(day=1)
    next_month = (month_anchor.replace(day=28) + timedelta(days=4)).replace(day=1)

    sessions = list(
        AttendanceSession.objects
        .filter(
            class_instance=class_instance,
            session_date__gte=month_start,
            session_date__lte=month_end,
        )
        .order_by("session_date", "start_time", "pk")
    )
    session_ids = [session.id for session in sessions]
    date_columns = [
        month_start + timedelta(days=offset)
        for offset in range((month_end - month_start).days + 1)
    ]

    active_student_ids = set(
        Enrollment.objects.filter(
            class_instance=class_instance,
            status=Enrollment.Status.ACTIVE,
        ).values_list("student_id", flat=True)
    )
    active_student_ids.update(
        AttendanceRecord.objects.filter(
            session_id__in=session_ids,
            context=AttendanceRecord.Context.REGULAR,
        ).values_list("student_id", flat=True)
    )
    students = list(
        Student.objects.filter(id__in=active_student_ids).order_by("last_name", "first_name")
    )

    record_map = {}
    monthly_records = list(
        AttendanceRecord.objects
        .filter(
            session_id__in=session_ids,
            context=AttendanceRecord.Context.REGULAR,
        )
        .select_related("student", "session")
    )
    for record in monthly_records:
        record_map[(record.student_id, record.session.session_date)] = record

    rows = []
    total_record_count = 0
    total_present_like = 0
    total_absent = 0
    for student in students:
        cells = []
        for day in date_columns:
            record = record_map.get((student.id, day))
            if record is None:
                cells.append(None)
                continue
            total_record_count += 1
            if record.status in {
                AttendanceRecord.Status.PRESENT,
                AttendanceRecord.Status.LATE,
                AttendanceRecord.Status.LEFT_EARLY,
            }:
                total_present_like += 1
            if record.status == AttendanceRecord.Status.ABSENT:
                total_absent += 1
            cells.append(record)
        rows.append({"student": student, "cells": cells})

    attendance_rate = round((total_present_like / total_record_count) * 100) if total_record_count else None

    return render(
        request,
        "attendance/submission_detail.html",
        {
            "studio": studio,
            "role": "administrator" if _is_studio_admin(request.user, studio) else "teacher",
            "is_admin": _is_studio_admin(request.user, studio),
            "class_instance": class_instance,
            "month_anchor": month_anchor,
            "month_label": _month_label(month_anchor),
            "previous_month": previous_month.strftime("%Y-%m"),
            "next_month": next_month.strftime("%Y-%m"),
            "date_columns": date_columns,
            "rows": rows,
            "session_count": len(sessions),
            "student_count": len(students),
            "attendance_rate": attendance_rate,
            "absence_count": total_absent,
            "status_short": STATUS_SHORT,
        },
    )


@login_required
def student_absence_detail(request, studio_slug, student_id):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    is_admin = _is_studio_admin(request.user, studio)
    class_ids = _teacher_class_ids(request.user, studio)

    student = get_object_or_404(Student, pk=student_id, studio=studio)
    if not is_admin:
        has_access = (
            student.enrollments.filter(class_instance_id__in=class_ids).exists()
            or student.attendance_records.filter(session__class_instance_id__in=class_ids).exists()
        )
        if not has_access:
            raise Http404

    selected_class_id = request.GET.get("class") or ""
    visible_class_ids = class_ids if not is_admin else list(
        Class.objects.filter(studio=studio, is_active=True).values_list("id", flat=True)
    )

    eligible_classes = (
        Class.objects
        .filter(studio=studio, id__in=visible_class_ids, is_active=True)
        .select_related("season")
        .order_by("name")
    )

    class_instance = None
    if selected_class_id:
        class_instance = get_object_or_404(
            Class.objects.select_related("season", "instructor"),
            pk=selected_class_id,
            studio=studio,
            id__in=visible_class_ids,
        )
    else:
        class_instance = (
            Class.objects
            .filter(
                studio=studio,
                id__in=visible_class_ids,
                attendance_sessions__records__student=student,
                attendance_sessions__records__status=AttendanceRecord.Status.ABSENT,
            )
            .select_related("season", "instructor")
            .distinct()
            .order_by("name")
            .first()
        )
        if class_instance:
            selected_class_id = str(class_instance.id)

    if class_instance is None:
        raise Http404

    month_anchor = _month_anchor(request.GET.get("month"))
    month_start, month_end = _month_bounds(month_anchor)
    previous_month = (month_anchor.replace(day=1) - timedelta(days=1)).replace(day=1)
    next_month = (month_anchor.replace(day=28) + timedelta(days=4)).replace(day=1)

    all_dates = [
        month_start + timedelta(days=offset)
        for offset in range((month_end - month_start).days + 1)
    ]

    records = list(
        AttendanceRecord.objects
        .filter(
            student=student,
            context=AttendanceRecord.Context.REGULAR,
            session__class_instance=class_instance,
            session__session_date__gte=month_start,
            session__session_date__lte=month_end,
        )
        .select_related("session", "session__class_instance")
        .order_by("session__session_date")
    )
    record_by_date = {
        record.session.session_date: record
        for record in records
    }

    chart_rows = [
        {
            "date": day,
            "record": record_by_date.get(day),
        }
        for day in all_dates
    ]

    detail_records = list(reversed(records))
    absence_total = sum(1 for record in records if record.status == AttendanceRecord.Status.ABSENT)
    present_like_total = sum(
        1
        for record in records
        if record.status in {
            AttendanceRecord.Status.PRESENT,
            AttendanceRecord.Status.LATE,
            AttendanceRecord.Status.LEFT_EARLY,
        }
    )
    attendance_rate = round((present_like_total / len(records)) * 100) if records else None

    makeups_owed = MakeupRequirement.objects.filter(
        student=student,
        source_class=class_instance,
        status=MakeupRequirement.Status.OUTSTANDING,
    ).count()

    return render(
        request,
        "attendance/student_absence_detail.html",
        {
            "studio": studio,
            "role": "administrator" if is_admin else "teacher",
            "is_admin": is_admin,
            "student": student,
            "class_instance": class_instance,
            "eligible_classes": eligible_classes,
            "selected_class_id": selected_class_id,
            "month_anchor": month_anchor,
            "month_label": _month_label(month_anchor),
            "previous_month": previous_month.strftime("%Y-%m"),
            "next_month": next_month.strftime("%Y-%m"),
            "chart_rows": chart_rows,
            "detail_records": detail_records,
            "absence_total": absence_total,
            "attendance_rate": attendance_rate,
            "makeups_owed": makeups_owed,
        },
    )


@login_required
def search_makeup_students(request, studio_slug, session_id):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    session = get_object_or_404(
        AttendanceSession.objects.select_related("class_instance", "class_instance__instructor", "class_instance__assistant_instructor"),
        pk=session_id,
        class_instance__studio=studio,
    )
    if _get_teacher_for_class(request.user, studio, session.class_instance) is None:
        raise Http404
    query = request.GET.get("q", "").strip()
    if len(query) < 2:
        return JsonResponse({"results": []})
    students = list(
        Student.objects
        .filter(studio=studio, is_active=True)
        .filter(models.Q(first_name__icontains=query) | models.Q(last_name__icontains=query))
        .exclude(attendance_records__session=session)
        .distinct()
        .order_by("last_name", "first_name")[:12]
    )
    results = []
    for student in students:
        requirement = (
            MakeupRequirement.objects
            .filter(student=student, status=MakeupRequirement.Status.OUTSTANDING)
            .select_related("source_class")
            .order_by("created_at")
            .first()
        )
        source_class = requirement.source_class if requirement else None
        if source_class is None:
            enrollment = (
                Enrollment.objects
                .filter(student=student, status=Enrollment.Status.ACTIVE)
                .exclude(class_instance=session.class_instance)
                .select_related("class_instance")
                .order_by("class_instance__name")
                .first()
            )
            source_class = enrollment.class_instance if enrollment else None
        results.append({
            "id": student.pk,
            "name": f"{student.first_name} {student.last_name}",
            "age": student.age,
            "source_class": f"{source_class.name} · {source_class.class_id}" if source_class else "No source class selected",
            "makeups_owed": outstanding_makeup_count(student),
        })
    return JsonResponse({"results": results})


@login_required
@transaction.atomic
def add_makeup_student(request, studio_slug, session_id):
    if request.method != "POST":
        raise Http404

    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    session = get_object_or_404(
        AttendanceSession.objects.select_related(
            "class_instance",
            "class_instance__instructor",
            "class_instance__assistant_instructor",
        ),
        pk=session_id,
        class_instance__studio=studio,
    )
    if _get_teacher_for_class(request.user, studio, session.class_instance) is None:
        raise Http404

    student = get_object_or_404(
        Student,
        pk=request.POST.get("student_id"),
        studio=studio,
        is_active=True,
    )

    try:
        record, created = add_makeup_student_to_session(
            session=session,
            student=student,
            added_by=request.user,
        )
    except ValueError as error:
        return JsonResponse({"ok": False, "error": str(error)}, status=400)

    return JsonResponse(
        {
            "ok": True,
            "created": created,
            "record_id": record.pk,
        }
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

    context = _attendance_history_context(
        student,
        studio,
        "family",
    )
    context.update(
        parent_portal_context(
            request,
            studio,
            selected_student=student,
            section="dashboard",
        )
    )

    return render(
        request,
        "attendance/parent_history.html",
        context,
    )



@login_required
def attendance_settings(request, studio_slug):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if not _is_studio_admin(request.user, studio):
        raise Http404

    is_admin = True
    policy, _ = AttendancePolicy.objects.get_or_create(studio=studio)
    email_templates = EmailTemplate.objects.filter(studio=studio, is_active=True).order_by("category", "name")
    if request.method == "POST":
        action = request.POST.get("action", "")
        if action in {
            "create_trigger",
            "update_trigger",
            "delete_trigger",
            "toggle_trigger",
        } and not is_admin:
            raise Http404

        if action in {"create_trigger", "update_trigger"}:
            try:
                threshold = int(request.POST.get("threshold_value", "3"))
            except (TypeError, ValueError):
                threshold = 3

            send_email_enabled = request.POST.get("send_email") == "on"
            email_template = None
            email_template_id = request.POST.get("email_template_id") or ""

            if send_email_enabled and email_template_id:
                email_template = get_object_or_404(
                    EmailTemplate,
                    pk=email_template_id,
                    studio=studio,
                    is_active=True,
                )

            values = {
                "name": (
                    request.POST.get("name", "").strip()
                    or "Consecutive Absence Alert"
                ),
                "threshold_value": max(1, min(threshold, 99)),
                "is_enabled": request.POST.get("is_enabled") == "on",
                "highlight_student": request.POST.get("highlight_student") == "on",
                "create_makeup_requirements": (
                    request.POST.get("create_makeup_requirements") == "on"
                ),
                "send_email": send_email_enabled,
                "create_parent_task": request.POST.get("create_parent_task") == "on",
                "notify_teacher": request.POST.get("notify_teacher") == "on",
                "email_template": email_template,
            }

            if action == "create_trigger":
                AttendanceAutomationTrigger.objects.create(
                    studio=studio,
                    **values,
                )
                messages.success(request, "Attendance automation created.")
            else:
                trigger = get_object_or_404(
                    AbsenceRequest,
    AttendanceAutomationTrigger,
                    pk=request.POST.get("trigger_id"),
                    studio=studio,
                )
                for field_name, value in values.items():
                    setattr(trigger, field_name, value)
                trigger.save()
                messages.success(request, "Attendance automation updated.")

        elif action == "delete_trigger":
            trigger = get_object_or_404(
                AbsenceRequest,
    AttendanceAutomationTrigger,
                pk=request.POST.get("trigger_id"),
                studio=studio,
            )
            trigger_name = trigger.name
            trigger.delete()
            messages.success(
                request,
                f"{trigger_name} deleted.",
            )

        elif action == "toggle_trigger":
            trigger = get_object_or_404(
                AbsenceRequest,
    AttendanceAutomationTrigger,
                pk=request.POST.get("trigger_id"),
                studio=studio,
            )
            trigger.is_enabled = not trigger.is_enabled
            trigger.save(update_fields=["is_enabled", "updated_at"])
            messages.success(request, f"{trigger.name} {'enabled' if trigger.is_enabled else 'disabled'}.")


        elif action == "save_attendance_policy":
            policy.teachers_can_assign_makeups = request.POST.get("teachers_can_assign_makeups") == "on"
            policy.save(update_fields=["teachers_can_assign_makeups", "updated_at"])
            messages.success(request, "Attendance permissions saved.")

        elif action == "add_makeup_rule":
            today = timezone.localdate()
            source_class = get_object_or_404(
                Class, pk=request.POST.get("source_class_id"), studio=studio,
                is_active=True, season__is_active=True,
                season__start_date__lte=today, season__end_date__gte=today,
            )
            selected_ids = request.POST.getlist("meeting_ids")
            meetings = list(ClassMeeting.objects.filter(
                pk__in=selected_ids, class_instance__studio=studio,
                class_instance__is_active=True, is_active=True,
                class_instance__season__is_active=True,
                class_instance__season__start_date__lte=today,
                class_instance__season__end_date__gte=today,
            ).select_related("class_instance"))
            if not meetings:
                messages.error(request, "Choose at least one active replacement class meeting.")
            else:
                count = 0
                for meeting in meetings:
                    rule, created = MakeupEligibilityRule.objects.update_or_create(
                        studio=studio, source_class=source_class, eligible_meeting=meeting,
                        defaults={"is_active": True},
                    )
                    count += int(created)
                messages.success(request, f"Make-up schedule saved. {count} new eligible meeting(s).")

        elif action == "remove_makeup_rule":
            rule = get_object_or_404(MakeupEligibilityRule, pk=request.POST.get("rule_id"), studio=studio)
            rule.delete()
            messages.success(request, "Make-up schedule rule removed.")

        else:
            raise Http404
        return redirect("attendance:settings", studio_slug=studio.slug)

    today = timezone.localdate()
    current_class_filter = {
        "studio": studio,
        "is_active": True,
        "season__is_active": True,
        "season__start_date__lte": today,
        "season__end_date__gte": today,
    }
    active_classes = list(
        Class.objects.filter(**current_class_filter)
        .select_related("season", "class_type", "level")
        .order_by("name", "class_id")
    )
    meeting_options = list(
        ClassMeeting.objects.filter(
            class_instance__studio=studio,
            class_instance__is_active=True,
            class_instance__season__is_active=True,
            class_instance__season__start_date__lte=today,
            class_instance__season__end_date__gte=today,
            is_active=True,
        ).select_related(
            "class_instance", "class_instance__season",
            "class_instance__class_type", "class_instance__level"
        ).order_by("class_instance__name", "day_of_week", "start_time")
    )
    class_type_options = sorted({(c.class_type_id, c.class_type.name) for c in active_classes}, key=lambda v: v[1].lower())
    level_options = sorted({(c.level_id, c.level.name if c.level_id else "No level") for c in active_classes}, key=lambda v: v[1].lower())
    return render(request, "attendance/settings.html", {
        "studio": studio, "role": "administrator", "is_admin": True,
        "settings_section": "attendance", "policy": policy,
        "active_classes": active_classes, "meeting_options": meeting_options,
        "class_type_options": class_type_options, "level_options": level_options,
        "rules": MakeupEligibilityRule.objects.filter(studio=studio)
            .select_related("source_class", "eligible_meeting", "eligible_meeting__class_instance"),
        "triggers": AttendanceAutomationTrigger.objects.filter(studio=studio)
            .select_related("email_template").order_by("threshold_value", "name"),
        "email_templates": email_templates,
    })


@login_required
def available_makeup_dates(request, studio_slug):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    is_admin = _is_studio_admin(request.user, studio)
    policy, _ = AttendancePolicy.objects.get_or_create(studio=studio)
    class_ids = _teacher_class_ids(request.user, studio)
    if not is_admin and (not policy.teachers_can_assign_makeups or not class_ids):
        raise Http404
    requirement = get_object_or_404(
        MakeupRequirement.objects.select_related("source_class"),
        pk=request.GET.get("requirement_id"), source_class__studio=studio,
        source_class_id__in=class_ids,
        status=MakeupRequirement.Status.OUTSTANDING,
    )
    meeting = get_object_or_404(
        ClassMeeting.objects.select_related("class_instance", "class_instance__season"),
        pk=request.GET.get("meeting_id"), class_instance__studio=studio,
    )
    if not MakeupEligibilityRule.objects.filter(
        source_class=requirement.source_class,
        eligible_meeting=meeting, studio=studio, is_active=True,
    ).exists():
        raise Http404
    return JsonResponse({"dates": [d.isoformat() for d in eligible_makeup_dates(
        source_class=requirement.source_class, meeting=meeting)]})
