from django.contrib.auth import get_user_model
from django.db import transaction
from django.template import Context, Template, TemplateSyntaxError
from django.utils import timezone
from django.utils.html import strip_tags

from communications.email_service import EncoreEmailError, send_email
from communications.models import WorkspaceNotification
from communications.notification_services import create_workspace_notification
from enrollments.models import Enrollment
from tasks.models import Task
from tasks.services import synchronize_task_assignments

from .makeup_task_services import sync_makeup_tasks

from .models import (
    AttendanceAutomationTrigger,
    AttendanceRecord,
    AttendanceSession,
    AttendanceTriggerEvent,
    MakeupAssignment,
    MakeupRequirement,
)

User = get_user_model()


@transaction.atomic
def create_attendance_session_with_roster(*, class_instance, session_date, taken_by=None, start_time=None):
    session, created = AttendanceSession.objects.get_or_create(
        class_instance=class_instance,
        session_date=session_date,
        start_time=start_time,
        defaults={"taken_by": taken_by},
    )

    if created:
        active_enrollments = (
            Enrollment.objects
            .filter(class_instance=class_instance, status=Enrollment.Status.ACTIVE)
            .select_related("student")
        )
        AttendanceRecord.objects.bulk_create([
            AttendanceRecord(
                session=session,
                student=enrollment.student,
                context=AttendanceRecord.Context.REGULAR,
                status=AttendanceRecord.Status.PRESENT,
                marked_by=taken_by,
            )
            for enrollment in active_enrollments
        ])

    ensure_scheduled_makeups_for_session(session, added_by=taken_by)
    return session, created


def enabled_consecutive_triggers(studio):
    return (
        AttendanceAutomationTrigger.objects
        .select_related("email_template", "email_template__signature")
        .filter(
            studio=studio,
            trigger_type=AttendanceAutomationTrigger.TriggerType.CONSECUTIVE_ABSENCES,
            is_enabled=True,
        )
        .order_by("threshold_value", "id")
    )


def warning_threshold_for_studio(studio):
    trigger = enabled_consecutive_triggers(studio).filter(highlight_student=True).first()
    return trigger.threshold_value if trigger else None


def prior_consecutive_absence_count(student, class_instance, *, before_session):
    records = (
        AttendanceRecord.objects
        .filter(
            student=student,
            session__class_instance=class_instance,
            session__is_finalized=True,
            context=AttendanceRecord.Context.REGULAR,
            session__session_date__lte=before_session.session_date,
        )
        .exclude(session=before_session)
        .select_related("session")
        .order_by("-session__session_date", "-session__start_time", "-pk")
    )
    count = 0
    for record in records:
        if record.status == AttendanceRecord.Status.ABSENT:
            count += 1
        else:
            break
    return count


def current_consecutive_absence_count(record):
    if record.context != AttendanceRecord.Context.REGULAR:
        return 0
    prior = prior_consecutive_absence_count(
        record.student,
        record.session.class_instance,
        before_session=record.session,
    )
    return prior + 1 if record.status == AttendanceRecord.Status.ABSENT else 0


def outstanding_makeup_count(student):
    return MakeupRequirement.objects.filter(
        student=student,
        status=MakeupRequirement.Status.OUTSTANDING,
    ).count()


def oldest_outstanding_requirement(student):
    return (
        MakeupRequirement.objects
        .filter(student=student, status=MakeupRequirement.Status.OUTSTANDING)
        .select_related("source_class")
        .order_by("created_at", "id")
        .first()
    )


def _default_source_class(student, makeup_class):
    enrollment = (
        Enrollment.objects
        .filter(student=student, status=Enrollment.Status.ACTIVE)
        .exclude(class_instance=makeup_class)
        .select_related("class_instance")
        .order_by("class_instance__name")
        .first()
    )
    return enrollment.class_instance if enrollment else None


@transaction.atomic
def add_makeup_student_to_session(*, session, student, added_by):
    if student.studio_id != session.class_instance.studio_id:
        raise ValueError("Student must belong to the same studio as the attendance session.")

    existing = AttendanceRecord.objects.filter(session=session, student=student).first()
    if existing:
        if existing.context == AttendanceRecord.Context.REGULAR:
            raise ValueError("This student is already on the regular class roster.")
        return existing, False

    requirement = oldest_outstanding_requirement(student)
    source_class = requirement.source_class if requirement else _default_source_class(student, session.class_instance)
    assignment = MakeupAssignment.objects.create(
        requirement=requirement,
        student=student,
        source_class=source_class,
        makeup_class=session.class_instance,
        scheduled_date=session.session_date,
        attendance_session=session,
        added_by=added_by,
        is_walk_in=True,
    )
    record = AttendanceRecord.objects.create(
        session=session,
        student=student,
        context=AttendanceRecord.Context.MAKEUP,
        makeup_assignment=assignment,
        status=AttendanceRecord.Status.PRESENT,
        marked_by=added_by,
    )
    assignment.attendance_record = record
    assignment.save(update_fields=["attendance_record"])
    return record, True


@transaction.atomic
def ensure_scheduled_makeups_for_session(session, *, added_by=None):
    assignments = (
        MakeupAssignment.objects
        .filter(
            makeup_class=session.class_instance,
            scheduled_date=session.session_date,
            status=MakeupAssignment.Status.SCHEDULED,
        )
        .select_related("student", "source_class", "requirement", "makeup_meeting")
    )
    for assignment in assignments:
        # Do not attach a booking for a different meeting held on the same date.
        if (assignment.makeup_meeting_id and session.start_time is not None
                and assignment.makeup_meeting.start_time != session.start_time):
            continue
        existing = AttendanceRecord.objects.filter(session=session, student=assignment.student).first()
        if existing:
            if existing.context == AttendanceRecord.Context.MAKEUP:
                assignment.attendance_session = session
                assignment.attendance_record = existing
                assignment.save(update_fields=["attendance_session", "attendance_record"])
            continue
        record = AttendanceRecord.objects.create(
            session=session,
            student=assignment.student,
            context=AttendanceRecord.Context.MAKEUP,
            makeup_assignment=assignment,
            status=AttendanceRecord.Status.PRESENT,
            marked_by=added_by,
        )
        assignment.attendance_session = session
        assignment.attendance_record = record
        assignment.save(update_fields=["attendance_session", "attendance_record"])


def _streak_absence_records(record, count):
    return list(
        AttendanceRecord.objects
        .filter(
            student=record.student,
            session__class_instance=record.session.class_instance,
            session__is_finalized=True,
            context=AttendanceRecord.Context.REGULAR,
            status=AttendanceRecord.Status.ABSENT,
            session__session_date__lte=record.session.session_date,
        )
        .select_related("session", "session__class_instance")
        .order_by("-session__session_date", "-session__start_time", "-pk")[:count]
    )


def _recipient_emails(student):
    addresses = []
    if student.user_id and student.user.email:
        addresses.append(student.user.email)
    if student.family_id:
        for guardian in student.family.guardians.filter(is_active=True, user__isnull=False).select_related("user"):
            if guardian.user.email:
                addresses.append(guardian.user.email)
    return list(dict.fromkeys(addresses))


def _render_trigger_email(trigger, event):
    template = trigger.email_template
    student = event.student
    class_instance = event.class_instance
    count = event.consecutive_count
    context = Context(
        {
            "trigger": trigger,
            "event": event,
            "student": student,
            "class_instance": class_instance,
            "studio": class_instance.studio,
            "consecutive_count": count,
            "makeup_count": count,
        }
    )

    if template:
        try:
            subject = Template(template.subject).render(context).strip()
            html_body = Template(template.html_body).render(context)
            text_body = (
                Template(template.text_body).render(context)
                if template.text_body
                else strip_tags(html_body)
            )
            signature = getattr(template, "signature", None)
            if signature and signature.body:
                html_body = f"{html_body}<div style='margin-top:24px'>{signature.body}</div>"
                text_body = f"{text_body}\n\n{strip_tags(signature.body)}"
            if subject and html_body:
                return subject, html_body, text_body
        except TemplateSyntaxError:
            pass

    subject = f"Attendance notice for {student.first_name}"
    html_body = (
        f"<p>{student.first_name} {student.last_name} has missed "
        f"{count} consecutive {class_instance.name} classes.</p>"
        f"<p>{count} makeup class{'es' if count != 1 else ''} "
        f"{'are' if count != 1 else 'is'} now required.</p>"
    )
    return subject, html_body, strip_tags(html_body)


def _send_absence_email(trigger, event):
    student = event.student
    recipients = _recipient_emails(student)
    if not recipients:
        return
    subject, html_body, text_body = _render_trigger_email(trigger, event)
    try:
        send_email(
            to=recipients,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            tags={"message_type": "attendance_alert", "source": "attendance"},
        )
    except EncoreEmailError:
        pass


def _create_makeup_task(event, finalized_by):
    student = event.student
    count = event.consecutive_count
    task = Task.objects.create(
        studio=event.class_instance.studio,
        title=f"Complete {count} makeup class{'es' if count != 1 else ''}",
        description=(
            f"{student.first_name} has missed {count} consecutive "
            f"{event.class_instance.name} classes and needs to complete "
            f"{count} makeup class{'es' if count != 1 else ''}."
        ),
        priority=Task.Priority.HIGH,
        created_by=finalized_by,
        context_type=Task.ContextType.STUDENT,
        audience_type=Task.AudienceType.RELATED_STUDENT,
        class_instance=event.class_instance,
        student=student,
        is_student_facing=True,
        notify_assignees=True,
    )
    role = "administrator" if finalized_by.studio_memberships.filter(
        studio=event.class_instance.studio,
        role="administrator",
        is_active=True,
    ).exists() else "teacher"
    synchronize_task_assignments(
        task,
        creator=finalized_by,
        role=role,
        selected_students=[student],
    )


def _notify_class_staff(event):
    class_instance = event.class_instance
    users = []
    for instructor in [class_instance.instructor, class_instance.assistant_instructor]:
        if instructor and instructor.user_id and instructor.user not in users:
            users.append(instructor.user)
    for user in users:
        create_workspace_notification(
            studio=class_instance.studio,
            user=user,
            category=WorkspaceNotification.Category.SYSTEM,
            kind="attendance_consecutive_absence",
            title="Attendance Alert",
            message=(
                f"{event.student.first_name} {event.student.last_name} has missed "
                f"{event.consecutive_count} consecutive days in {class_instance.name} "
                "and needs a makeup class."
            ),
            action_url=f"/attendance/{class_instance.studio.slug}/manager/?tab=absences",
            dedupe_key=f"attendance-trigger-{event.pk}-{user.pk}",
        )


@transaction.atomic
def process_finalized_regular_absence(record, *, finalized_by):
    if record.context != AttendanceRecord.Context.REGULAR or record.status not in {
        AttendanceRecord.Status.ABSENT, AttendanceRecord.Status.EXCUSED,
    }:
        return []
    if record.status == AttendanceRecord.Status.EXCUSED:
        from .models import AbsenceRequestSession, AbsenceRequest
        requires = AbsenceRequestSession.objects.filter(
            student=record.student, class_instance=record.session.class_instance,
            session_date=record.session.session_date,
            request__status=AbsenceRequest.Status.APPROVED, request__require_makeups=True,
        ).exists()
        if not requires:
            return []

    # An ordinary finalized absence creates one make-up obligation, without
    # depending on the optional consecutive-absence automation threshold.
    from .models import AbsenceRequestSession, AbsenceRequest
    approved = AbsenceRequestSession.objects.filter(
        student=record.student, class_instance=record.session.class_instance,
        session_date=record.session.session_date,
        request__status=AbsenceRequest.Status.APPROVED,
    ).select_related("request").first()
    if approved is None or approved.request.require_makeups:
        requirement = MakeupRequirement.objects.filter(source_attendance_record=record).first()
        if requirement is None and approved is not None:
            requirement = MakeupRequirement.objects.filter(absence_request_session=approved).first()
        if requirement is None:
            requirement = MakeupRequirement.objects.create(
                student=record.student, source_class=record.session.class_instance,
                source_attendance_record=record, absence_request_session=approved,
            )
            # Notify linked guardians and the student once for this absence.
            recipients = []
            if record.student.user_id:
                recipients.append(record.student.user)
            if record.student.family_id:
                from families.models import Guardian
                recipients.extend(g.user for g in Guardian.objects.filter(
                    family_id=record.student.family_id, is_active=True,
                    user__isnull=False).select_related("user"))
            for user in {u.pk: u for u in recipients}.values():
                create_workspace_notification(
                    studio=record.session.class_instance.studio, user=user,
                    category=WorkspaceNotification.Category.SYSTEM,
                    kind="attendance_makeup_required",
                    title="Make-Up Class Required",
                    message=f"{record.student.first_name} has a make-up to schedule for {record.session.class_instance.name}.",
                    action_url=f"/attendance/{record.session.class_instance.studio.slug}/makeups/",
                    dedupe_key=f"attendance-makeup-required-{requirement.pk}-{user.pk}",
                )
        elif requirement.source_attendance_record_id is None:
            requirement.source_attendance_record = record
            requirement.save(update_fields=["source_attendance_record"])
        sync_makeup_tasks(record.student)

    if record.status != AttendanceRecord.Status.ABSENT:
        return []
    consecutive_count = current_consecutive_absence_count(record)
    fired = []
    for trigger in enabled_consecutive_triggers(record.session.class_instance.studio):
        if consecutive_count != trigger.threshold_value:
            continue
        event, created = AttendanceTriggerEvent.objects.get_or_create(
            trigger=trigger,
            attendance_record=record,
            defaults={
                "student": record.student,
                "class_instance": record.session.class_instance,
                "consecutive_count": consecutive_count,
            },
        )
        if not created:
            continue
        fired.append(event)

        if trigger.create_makeup_requirements:
            for absence_record in _streak_absence_records(record, consecutive_count):
                MakeupRequirement.objects.get_or_create(
                    source_attendance_record=absence_record,
                    defaults={
                        "student": absence_record.student,
                        "source_class": absence_record.session.class_instance,
                        "trigger": trigger,
                    },
                )
        if trigger.send_email:
            _send_absence_email(trigger, event)
        if trigger.create_parent_task:
            _create_makeup_task(event, finalized_by)
        if trigger.notify_teacher:
            _notify_class_staff(event)
    if MakeupRequirement.objects.filter(student=record.student).exists():
        sync_makeup_tasks(record.student)
    return fired


@transaction.atomic
def process_finalized_makeup_record(record):
    if record.context != AttendanceRecord.Context.MAKEUP or not record.makeup_assignment_id:
        return
    assignment = record.makeup_assignment
    if record.status in {AttendanceRecord.Status.PRESENT, AttendanceRecord.Status.LATE, AttendanceRecord.Status.LEFT_EARLY}:
        assignment.status = MakeupAssignment.Status.COMPLETED
        assignment.completed_at = timezone.now()
        assignment.save(update_fields=["status", "completed_at"])
        if assignment.requirement_id and assignment.requirement.status == MakeupRequirement.Status.OUTSTANDING:
            requirement = assignment.requirement
            requirement.status = MakeupRequirement.Status.COMPLETED
            requirement.completed_at = timezone.now()
            requirement.save(update_fields=["status", "completed_at"])
    elif record.status in {AttendanceRecord.Status.ABSENT, AttendanceRecord.Status.EXCUSED}:
        assignment.status = MakeupAssignment.Status.MISSED
        assignment.completed_at = None
        assignment.save(update_fields=["status", "completed_at"])
    if assignment.requirement_id:
        sync_makeup_tasks(record.student)


# Makeup bookings are one-time attendance visits, not enrollments: there is deliberately
# no destination-class capacity or enrollment check here.
def eligible_makeup_dates(*, source_class, meeting, days_ahead=84, today=None):
    from datetime import timedelta
    from scheduling.models import ClassOccurrenceOverride

    today = today or timezone.localdate()
    if (not source_class.is_active or not meeting.is_active or
            not meeting.class_instance.is_active or
            source_class.studio_id != meeting.class_instance.studio_id):
        return []
    season = meeting.class_instance.season
    if not season.is_active:
        return []
    first = today + timedelta(days=(meeting.day_of_week - today.weekday()) % 7)
    end = min(today + timedelta(days=days_ahead), season.end_date)
    result = []
    day = first
    while day <= end:
        if day >= season.start_date and not ClassOccurrenceOverride.objects.filter(
            class_instance=meeting.class_instance,
            meeting=meeting,
            occurrence_date=day,
            status=ClassOccurrenceOverride.Status.CANCELLED,
        ).exists():
            result.append(day)
        day += timedelta(days=7)
    return result


def validate_makeup_booking(*, source_class, meeting, booked_date):
    from .models import MakeupEligibilityRule
    if not MakeupEligibilityRule.objects.filter(
        studio=source_class.studio, source_class=source_class,
        eligible_meeting=meeting, is_active=True,
    ).exists():
        raise ValueError("This meeting is not approved for that missed class.")
    if booked_date not in eligible_makeup_dates(source_class=source_class, meeting=meeting):
        raise ValueError("That make-up session is not available or has been cancelled.")
