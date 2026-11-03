from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [("attendance", "0004_attendance_policy_eligibility"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(name="AbsenceRequest", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("reason", models.TextField()),
            ("status", models.CharField(choices=[("pending", "Pending Review"), ("approved", "Approved"), ("denied", "Denied")], default="pending", max_length=12)),
            ("reviewed_at", models.DateTimeField(blank=True, null=True)),
            ("review_comment", models.TextField(blank=True)),
            ("require_makeups", models.BooleanField(default=False)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("studio", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="absence_requests", to="studios.studio")),
            ("submitted_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="submitted_absence_requests", to=settings.AUTH_USER_MODEL)),
            ("reviewed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reviewed_absence_requests", to=settings.AUTH_USER_MODEL)),
        ], options={"ordering": ["-created_at"]}),
        migrations.CreateModel(name="AbsenceRequestSession", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("session_date", models.DateField()),
            ("request", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="sessions", to="attendance.absencerequest")),
            ("student", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="requested_absences", to="students.student")),
            ("class_instance", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="requested_absences", to="classes.class")),
            ("meeting", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="requested_absences", to="classes.classmeeting")),
        ], options={"ordering": ["session_date", "class_instance__name"]}),
        migrations.AddConstraint(model_name="absencerequestsession", constraint=models.UniqueConstraint(fields=("request", "student", "meeting", "session_date"), name="unique_absence_request_session")),
    ]
