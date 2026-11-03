"""Preview or create missing makeup requirements for previously finalized absences.

Run with --studio SLUG to preview, then --apply to commit. Only current
active seasons are included, to avoid reopening archival obligations.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from attendance.models import (
    AbsenceRequest, AbsenceRequestSession, AttendanceRecord, MakeupRequirement,
)
from attendance.makeup_task_services import sync_makeup_tasks
from studios.models import Studio


class Command(BaseCommand):
    help = "Preview/backfill make-up requirements for finalized regular absences in active seasons."

    def add_arguments(self, parser):
        parser.add_argument("--studio", required=True)
        parser.add_argument("--apply", action="store_true", help="Create missing requirements (default dry-run).")

    @transaction.atomic
    def handle(self, *args, **options):
        studio = Studio.objects.filter(slug=options["studio"], is_active=True).first()
        if studio is None:
            raise CommandError("Active studio not found")
        today = timezone.localdate()
        queryset = AttendanceRecord.objects.filter(
            session__class_instance__studio=studio,
            session__class_instance__season__is_active=True,
            session__class_instance__season__start_date__lte=today,
            session__class_instance__season__end_date__gte=today,
            session__is_finalized=True,
            context=AttendanceRecord.Context.REGULAR,
            status=AttendanceRecord.Status.ABSENT,
            makeup_requirement__isnull=True,
        ).select_related("student", "session", "session__class_instance")
        count = 0
        affected = set()
        for record in queryset.iterator():
            approval = AbsenceRequestSession.objects.filter(
                student=record.student, class_instance=record.session.class_instance,
                session_date=record.session.session_date,
                request__status=AbsenceRequest.Status.APPROVED,
            ).select_related("request").first()
            if approval and not approval.request.require_makeups:
                continue
            if approval and MakeupRequirement.objects.filter(absence_request_session=approval).exists():
                continue
            count += 1
            if options["apply"]:
                MakeupRequirement.objects.get_or_create(
                    source_attendance_record=record,
                    defaults={"student": record.student,
                              "source_class": record.session.class_instance,
                              "absence_request_session": approval},
                )
                affected.add(record.student_id)
        if options["apply"]:
            from students.models import Student
            for student in Student.objects.filter(pk__in=affected, studio=studio):
                sync_makeup_tasks(student)
        self.stdout.write(self.style.SUCCESS(
            f'{"Created" if options["apply"] else "Would create"} {count} missing requirements; '
            f'{"tasks synchronized" if options["apply"] else "no changes made"}.'
        ))
