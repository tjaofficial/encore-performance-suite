from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("attendance", "0003_attendance_trigger_email_template"),
        ("classes", "0001_initial"),
        ("studios", "0001_initial"),
    ]
    operations = [
        migrations.CreateModel(
            name="AttendancePolicy",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("teachers_can_assign_makeups", models.BooleanField(default=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("studio", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="attendance_policy", to="studios.studio")),
            ],
        ),
        migrations.CreateModel(
            name="MakeupEligibilityRule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("eligible_meeting", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="makeup_eligibility_rules", to="classes.classmeeting")),
                ("source_class", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="makeup_eligibility_rules", to="classes.class")),
                ("studio", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="makeup_eligibility_rules", to="studios.studio")),
            ],
            options={"ordering": ["source_class__name", "eligible_meeting__day_of_week", "eligible_meeting__start_time"]},
        ),
        migrations.AddField(
            model_name="makeupassignment", name="makeup_meeting",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="makeup_assignments", to="classes.classmeeting"),
        ),
        migrations.AddConstraint(
            model_name="makeupeligibilityrule",
            constraint=models.UniqueConstraint(fields=("source_class", "eligible_meeting"), name="unique_makeup_eligible_meeting"),
        ),
    ]
