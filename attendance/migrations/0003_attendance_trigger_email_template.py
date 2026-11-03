from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("communications", "0001_initial"),
        ("attendance", "0002_attendance_automation_makeups"),
    ]

    operations = [
        migrations.AddField(
            model_name="attendanceautomationtrigger",
            name="email_template",
            field=models.ForeignKey(
                blank=True,
                limit_choices_to={"category": "attendance"},
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="attendance_automation_triggers",
                to="communications.emailtemplate",
            ),
        ),
    ]
