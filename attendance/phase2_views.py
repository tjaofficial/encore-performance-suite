"""Family/student make-up booking, absence requests, and admin review."""
import json
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from classes.models import ClassMeeting
from communications.models import WorkspaceNotification
from communications.notification_services import administrator_users, create_workspace_notification, notify_student_guardians
from dashboard.parent_portal import parent_portal_context
from enrollments.models import Enrollment
from families.models import Guardian
from students.models import Student
from studios.models import Studio
from scheduling.models import ClassOccurrenceOverride
from .models import AbsenceRequest, AbsenceRequestSession, AttendanceRecord, MakeupAssignment, MakeupEligibilityRule, MakeupRequirement
from .services import eligible_makeup_dates, validate_makeup_booking
from .makeup_task_services import sync_makeup_tasks


def _role(request, studio):
    role = request.session.get("encore_workspace_role")
    if request.session.get("encore_workspace_studio_slug") != studio.slug:
        return None
    if request.user.is_superuser and role == "administrator":
        return role
    if role in {"administrator", "family", "student"} and request.user.studio_memberships.filter(studio=studio, role=role, is_active=True).exists():
        return role
    return None


def _students(request, studio, role):
    if role == "family":
        family_ids = Guardian.objects.filter(user=request.user, is_active=True, family__studio=studio).values_list("family_id", flat=True)
        return Student.objects.filter(studio=studio, family_id__in=family_ids, is_active=True).distinct()
    if role == "student":
        return Student.objects.filter(studio=studio, user=request.user, is_active=True)
    return Student.objects.none()


def _notify(studio, users, title, message, url, key):
    for user in users:
        if user:
            create_workspace_notification(studio=studio, user=user, category=WorkspaceNotification.Category.SYSTEM,
                kind="attendance_absence_request", title=title, message=message,
                action_url=url, dedupe_key=f"{key}:{user.pk}")


def _parent_receivers(students):
    ids = set()
    users = []
    for student in students:
        if student.user_id and student.user_id not in ids:
            users.append(student.user); ids.add(student.user_id)
        if student.family_id:
            for guardian in Guardian.objects.filter(family_id=student.family_id, is_active=True, user__isnull=False).select_related("user"):
                if guardian.user_id not in ids:
                    users.append(guardian.user); ids.add(guardian.user_id)
    return users


def _active_enrollments(students):
    today = timezone.localdate()
    return Enrollment.objects.filter(student__in=students, status=Enrollment.Status.ACTIVE,
        class_instance__is_active=True, class_instance__season__is_active=True,
        class_instance__season__end_date__gte=today).select_related("student", "class_instance", "class_instance__season").prefetch_related("class_instance__meeting_times")


def _session_options(students, days_ahead=120):
    """Only actual weekly class dates, not arbitrary dates. Never apply class capacity."""
    today = timezone.localdate()
    end = today + timedelta(days=days_ahead)
    options = []
    already_requested = set(
        AbsenceRequestSession.objects.filter(
            student__in=students,
            request__status__in=[AbsenceRequest.Status.PENDING, AbsenceRequest.Status.APPROVED],
        ).values_list("student_id", "class_instance_id", "session_date")
    )
    for enrollment in _active_enrollments(students):
        cls = enrollment.class_instance
        for meeting in cls.meeting_times.all():
            if not meeting.is_active:
                continue
            day = today + timedelta(days=(meeting.day_of_week - today.weekday()) % 7)
            while day <= min(end, cls.season.end_date):
                if (day >= cls.season.start_date
                    and (enrollment.student_id, cls.pk, day) not in already_requested
                    and not ClassOccurrenceOverride.objects.filter(
                    class_instance=cls, meeting=meeting, occurrence_date=day,
                    status=ClassOccurrenceOverride.Status.CANCELLED).exists()):
                    options.append({"student_id": enrollment.student_id, "student": str(enrollment.student),
                        "class_id": cls.id, "class": cls.name, "meeting_id": meeting.id,
                        "date": day.isoformat(), "time": meeting.start_time.strftime("%I:%M %p").lstrip("0")})
                day += timedelta(days=7)
    return options


@login_required
def makeup_schedule(request, studio_slug):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    role = _role(request, studio)
    if role not in {"family", "student"}:
        raise Http404
    students = list(_students(request, studio, role))
    portal = parent_portal_context(request, studio, section="makeups") if role == "family" else {}
    selected_student = portal.get("selected_student") if role == "family" else (students[0] if students else None)
    if selected_student is not None:
        students = [selected_student]
    for student in students:
        sync_makeup_tasks(student)
    requirements = list(MakeupRequirement.objects.filter(student__in=students, status=MakeupRequirement.Status.OUTSTANDING)
        .select_related("student", "source_class", "source_attendance_record__session")
        .prefetch_related("assignments"))
    booked_dates_by_student = {
        student.pk: set(MakeupAssignment.objects.filter(
            student=student, status__in=[MakeupAssignment.Status.SCHEDULED, MakeupAssignment.Status.COMPLETED],
        ).values_list("scheduled_date", flat=True)) for student in students
    }
    for req in requirements:
        req.current_booking = next((a for a in req.assignments.all() if a.status == MakeupAssignment.Status.SCHEDULED), None)
        req.eligible_sessions = []
        if not req.current_booking:
            for rule in (MakeupEligibilityRule.objects.filter(studio=studio, source_class=req.source_class,
                    is_active=True, eligible_meeting__is_active=True, eligible_meeting__class_instance__is_active=True)
                    .select_related("eligible_meeting", "eligible_meeting__class_instance")):

                for dt in eligible_makeup_dates(source_class=req.source_class, meeting=rule.eligible_meeting):
                    if dt in booked_dates_by_student.get(req.student_id, set()):
                        continue
                    req.eligible_sessions.append({"meeting": rule.eligible_meeting, "date": dt,
                        "label": f"{rule.eligible_meeting.class_instance.name} · {dt:%a %b %d} · {rule.eligible_meeting.start_time:%I:%M %p}"})
            req.eligible_sessions.sort(key=lambda x: (x["date"], x["meeting"].start_time))
    requests = AbsenceRequest.objects.filter(studio=studio, sessions__student__in=students).distinct().prefetch_related("sessions")[:30]
    context = {"studio": studio, "role": role, "students": students, "requirements": requirements,
        "absence_requests": requests, "parent_section": "makeups"}
    if role == "family":
        context.update(portal)
        template = "attendance/family_makeup_schedule.html"
    else:
        template = "attendance/student_makeup_schedule.html"
    return render(request, template, context)


@login_required
@require_POST
@transaction.atomic
def book_makeup(request, studio_slug):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    role = _role(request, studio)
    if role not in {"family", "student"}:
        raise Http404
    requirement = get_object_or_404(MakeupRequirement.objects.select_for_update().select_related("student", "source_class"),
        pk=request.POST.get("requirement_id"), student__in=_students(request, studio, role),
        status=MakeupRequirement.Status.OUTSTANDING)
    Student.objects.select_for_update().get(pk=requirement.student_id)
    meeting = get_object_or_404(ClassMeeting.objects.select_related("class_instance", "class_instance__season"),
        pk=request.POST.get("meeting_id"), class_instance__studio=studio)
    try:
        scheduled_date = date.fromisoformat(request.POST.get("scheduled_date", ""))
        validate_makeup_booking(source_class=requirement.source_class, meeting=meeting, booked_date=scheduled_date)
        if MakeupAssignment.objects.filter(requirement=requirement, status__in=["scheduled", "completed"]).exists():
            raise ValueError("This make-up is already booked or completed.")
        if MakeupAssignment.objects.filter(
            student=requirement.student, scheduled_date=scheduled_date,
            status__in=[MakeupAssignment.Status.SCHEDULED, MakeupAssignment.Status.COMPLETED],
        ).exists():
            raise ValueError("This student already has a make-up scheduled on that date. Choose another day.")
        MakeupAssignment.objects.create(requirement=requirement, student=requirement.student,
            source_class=requirement.source_class, makeup_class=meeting.class_instance,
            makeup_meeting=meeting, scheduled_date=scheduled_date, added_by=request.user)
        sync_makeup_tasks(requirement.student)
        schedule_url = reverse("attendance:makeup_schedule", kwargs={"studio_slug": studio.slug}) + f"?student={requirement.student_id}"
        notify_student_guardians(
            requirement.student, kind="makeup_scheduled", title="Make-Up Class Scheduled",
            message=(f"{requirement.student.first_name}: {meeting.class_instance.name} "
                     f"on {scheduled_date:%b %d, %Y} at {meeting.start_time:%I:%M %p}."),
            action_url=schedule_url, event_key=f"makeup-booked:{requirement.pk}:{meeting.pk}:{scheduled_date.isoformat()}",
        )
        messages.success(request, "Make-up session scheduled. It will appear on the teacher's attendance sheet.")
    except (ValueError, TypeError) as exc:
        messages.error(request, str(exc) or "Select a valid make-up session.")
    destination = reverse("attendance:makeup_schedule", kwargs={"studio_slug": studio.slug})
    if role == "family":
        destination += f"?student={requirement.student_id}"
    return redirect(destination)


@login_required
def absence_request_create(request, studio_slug):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    role = _role(request, studio)
    if role not in {"family", "student"}:
        raise Http404
    students = list(_students(request, studio, role))
    options = _session_options(students)
    if request.method == "POST":
        try:
            selected = json.loads(request.POST.get("selected_sessions", "[]"))
            reason = request.POST.get("reason", "").strip()
            if not reason:
                raise ValueError("Please explain the reason for the absence.")
            if not isinstance(selected, list) or not selected or len(selected) > 100:
                raise ValueError("Select between 1 and 100 class dates.")
            allowed = {(r["student_id"], r["meeting_id"], r["date"]): r for r in options}
            distinct = set()
            for item in selected:
                key = (int(item["student_id"]), int(item["meeting_id"]), str(item["date"]))
                if key not in allowed:
                    raise ValueError("One of the requested dates is not part of a current enrollment.")
                distinct.add(key)
            with transaction.atomic():
                list(Student.objects.select_for_update().filter(pk__in=[key[0] for key in distinct]).order_by("pk"))
                existing = set(AbsenceRequestSession.objects.filter(
                    student_id__in=[key[0] for key in distinct],
                    request__status__in=[AbsenceRequest.Status.PENDING, AbsenceRequest.Status.APPROVED],
                ).values_list("student_id", "class_instance_id", "session_date"))
                if any((sid, allowed[(sid, mid, day)]["class_id"], date.fromisoformat(day)) in existing
                       for sid, mid, day in distinct):
                    raise ValueError("A selected class date was already requested. Refresh and choose another date.")
                obj = AbsenceRequest.objects.create(studio=studio, submitted_by=request.user, reason=reason)
                for key in distinct:
                    row = allowed[key]
                    AbsenceRequestSession.objects.create(request=obj, student_id=key[0], meeting_id=key[1],
                        class_instance_id=row["class_id"], session_date=date.fromisoformat(key[2]))
                url = reverse("attendance:manager", kwargs={"studio_slug": studio.slug}) + "?tab=requests"
                _notify(studio, administrator_users(studio), "New Absence Request",
                    f"A family submitted an absence request covering {len(distinct)} class session(s).", url, f"absence-request:{obj.pk}")
            messages.success(request, "Absence request submitted to the studio for review.")
            return redirect("attendance:makeup_schedule", studio_slug=studio.slug)
        except (ValueError, KeyError, TypeError) as exc:
            messages.error(request, str(exc) or "Please check the selected dates.")
    context = {"studio": studio, "role": role, "options_json": json.dumps(options), "students": students,
        "parent_section": "makeups"}
    if role == "family":
        context.update(parent_portal_context(request, studio, section="makeups"))
        template = "attendance/family_absence_request.html"
    else:
        template = "attendance/student_absence_request.html"
    return render(request, template, context)


@login_required
@require_POST
@transaction.atomic
def review_absence_request(request, studio_slug, request_id):
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if _role(request, studio) != "administrator":
        raise Http404
    obj = get_object_or_404(AbsenceRequest.objects.select_for_update(), pk=request_id, studio=studio, status="pending")
    decision = request.POST.get("decision")
    if decision not in {"approved", "denied"}:
        raise Http404
    obj.status = decision
    obj.review_comment = request.POST.get("comment", "").strip()[:2000]
    obj.reviewed_by = request.user
    obj.reviewed_at = timezone.now()
    obj.require_makeups = decision == "approved" and request.POST.get("require_makeups") == "on"
    obj.save(update_fields=["status", "review_comment", "reviewed_by", "reviewed_at", "require_makeups"])
    affected = list(obj.sessions.select_related("student", "class_instance", "meeting"))
    # Existing finalized records may be resolved now. Future attendance remains untouched until taken.
    if decision == "approved":
        for item in affected:
            record = AttendanceRecord.objects.filter(student=item.student, session__class_instance=item.class_instance,
                session__session_date=item.session_date, session__is_finalized=True,
                context=AttendanceRecord.Context.REGULAR).first()
            if record and not obj.require_makeups:
                existing_req = MakeupRequirement.objects.filter(source_attendance_record=record,
                    status=MakeupRequirement.Status.OUTSTANDING).first()
                if existing_req:
                    existing_req.status = MakeupRequirement.Status.WAIVED
                    existing_req.save(update_fields=["status"])
                if record.status == AttendanceRecord.Status.ABSENT:
                    record.status = AttendanceRecord.Status.EXCUSED
                    record.save(update_fields=["status", "marked_at"])
            if obj.require_makeups:
                requirement = MakeupRequirement.objects.filter(absence_request_session=item).first()
                if requirement is None and record is not None:
                    requirement = MakeupRequirement.objects.filter(source_attendance_record=record).first()
                if requirement is None:
                    requirement = MakeupRequirement.objects.create(
                        student=item.student, source_class=item.class_instance,
                        source_attendance_record=record,
                        absence_request_session=item,
                    )
                else:
                    changes = []
                    if requirement.absence_request_session_id != item.pk:
                        requirement.absence_request_session = item
                        changes.append("absence_request_session")
                    if record and requirement.source_attendance_record_id is None:
                        requirement.source_attendance_record = record
                        changes.append("source_attendance_record")
                    if changes:
                        requirement.save(update_fields=changes)
    for student in {item.student for item in affected}:
        sync_makeup_tasks(student)
    recipients = _parent_receivers([item.student for item in affected])
    url = reverse("attendance:makeup_schedule", kwargs={"studio_slug": studio.slug})
    _notify(studio, recipients, f"Absence Request {obj.get_status_display()}",
        obj.review_comment or f"The studio {decision} your absence request for {len(affected)} class session(s).",
        url, f"absence-decision:{obj.pk}")
    messages.success(request, "Absence request reviewed. Families have been notified.")
    return redirect(reverse("attendance:manager", kwargs={"studio_slug": studio.slug}) + "?tab=requests")


@login_required
def family_attendance(request, studio_slug):
    """Student-specific attendance overview in the existing family portal."""
    studio = get_object_or_404(Studio, slug=studio_slug, is_active=True)
    if _role(request, studio) != "family":
        raise Http404
    portal = parent_portal_context(request, studio, section="attendance")
    student = portal.get("selected_student")
    if not student:
        raise Http404
    from django.db.models import Count, Q
    from .models import AttendanceSession
    records = (AttendanceRecord.objects.filter(
        student=student, context=AttendanceRecord.Context.REGULAR,
        session__class_instance__studio=studio,
        session__is_finalized=True,
    ).select_related("session", "session__class_instance").order_by("-session__session_date", "-pk"))
    present_statuses = [AttendanceRecord.Status.PRESENT, AttendanceRecord.Status.LATE, AttendanceRecord.Status.LEFT_EARLY]
    total = records.count()
    present = records.filter(status__in=present_statuses).count()
    absent = records.filter(status=AttendanceRecord.Status.ABSENT).count()
    excused = records.filter(status=AttendanceRecord.Status.EXCUSED).count()
    makeups = MakeupRequirement.objects.filter(student=student)
    outstanding = makeups.filter(status=MakeupRequirement.Status.OUTSTANDING)
    requirement_ids = list(outstanding.values_list("id", flat=True))
    scheduled = MakeupAssignment.objects.filter(requirement_id__in=requirement_ids, status=MakeupAssignment.Status.SCHEDULED).count()
    completed = makeups.filter(status=MakeupRequirement.Status.COMPLETED).count()
    context = {
        **portal, "studio": studio, "role": "family", "student": student,
        "stats": {"rate": round(present / total * 100) if total else None,
                  "total": total, "present": present, "absent": absent, "excused": excused},
        "recent_records": records[:20],
        "makeup": {"outstanding": outstanding.count(), "scheduled": scheduled, "completed": completed,
                   "to_schedule": max(outstanding.count() - scheduled, 0)},
    }
    return render(request, "attendance/family_attendance.html", context)
