from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [("attendance", "0005_absence_requests")]
    operations = [
        migrations.AlterField(model_name="makeuprequirement", name="source_attendance_record",
            field=models.OneToOneField(to="attendance.attendancerecord", on_delete=django.db.models.deletion.CASCADE,
                related_name="makeup_requirement", null=True, blank=True)),
        migrations.AddField(model_name="makeuprequirement", name="absence_request_session",
            field=models.OneToOneField(to="attendance.absencerequestsession", on_delete=django.db.models.deletion.SET_NULL,
                related_name="makeup_requirement", null=True, blank=True)),
    ]
