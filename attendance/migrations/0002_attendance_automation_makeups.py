from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("attendance", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="AttendanceAutomationTrigger",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(default="Consecutive Absence Alert", max_length=160)),
                ("trigger_type", models.CharField(choices=[("consecutive_absences", "Consecutive Absences")], default="consecutive_absences", max_length=40)),
                ("threshold_value", models.PositiveSmallIntegerField(default=3)),
                ("is_enabled", models.BooleanField(default=True)),
                ("highlight_student", models.BooleanField(default=True)),
                ("create_makeup_requirements", models.BooleanField(default=True)),
                ("send_email", models.BooleanField(default=True)),
                ("create_parent_task", models.BooleanField(default=True)),
                ("notify_teacher", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("studio", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="attendance_automation_triggers", to="studios.studio")),
            ],
            options={"ordering": ["threshold_value", "name"]},
        ),
        migrations.CreateModel(
            name="MakeupRequirement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("outstanding", "Outstanding"), ("completed", "Completed"), ("waived", "Waived")], default="outstanding", max_length=20)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("source_attendance_record", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="makeup_requirement", to="attendance.attendancerecord")),
                ("source_class", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="makeup_requirements", to="classes.class")),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="makeup_requirements", to="students.student")),
                ("trigger", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="makeup_requirements", to="attendance.attendanceautomationtrigger")),
            ],
            options={"ordering": ["created_at", "id"]},
        ),
        migrations.CreateModel(
            name="MakeupAssignment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("scheduled_date", models.DateField()),
                ("is_walk_in", models.BooleanField(default=False)),
                ("status", models.CharField(choices=[("scheduled", "Scheduled"), ("completed", "Completed"), ("missed", "Missed"), ("cancelled", "Cancelled")], default="scheduled", max_length=20)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("added_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="makeup_assignments_added", to=settings.AUTH_USER_MODEL)),
                ("attendance_record", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="makeup_assignment_result", to="attendance.attendancerecord")),
                ("attendance_session", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="makeup_assignments", to="attendance.attendancesession")),
                ("makeup_class", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="makeup_students_received", to="classes.class")),
                ("requirement", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="assignments", to="attendance.makeuprequirement")),
                ("source_class", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="makeup_students_sent", to="classes.class")),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="makeup_assignments", to="students.student")),
            ],
            options={"ordering": ["scheduled_date", "student__last_name", "student__first_name"]},
        ),
        migrations.AddField(
            model_name="attendancerecord",
            name="context",
            field=models.CharField(choices=[("regular", "Regular Class"), ("makeup", "Makeup Class")], default="regular", max_length=20),
        ),
        migrations.AddField(
            model_name="attendancerecord",
            name="makeup_assignment",
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="attendance", to="attendance.makeupassignment"),
        ),
        migrations.CreateModel(
            name="AttendanceTriggerEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("consecutive_count", models.PositiveSmallIntegerField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("attendance_record", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="trigger_events", to="attendance.attendancerecord")),
                ("class_instance", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="attendance_trigger_events", to="classes.class")),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="attendance_trigger_events", to="students.student")),
                ("trigger", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="events", to="attendance.attendanceautomationtrigger")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddConstraint(
            model_name="attendancetriggerevent",
            constraint=models.UniqueConstraint(fields=("trigger", "attendance_record"), name="unique_attendance_trigger_event_per_record"),
        ),
    ]
