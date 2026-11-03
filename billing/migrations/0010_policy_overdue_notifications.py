from django.db import migrations, models


def copy_legacy_settings(apps, schema_editor):
    TuitionPlan = apps.get_model("billing", "TuitionPlan")
    StudioTuitionSettings = apps.get_model("billing", "StudioTuitionSettings")
    for settings in StudioTuitionSettings.objects.all().iterator():
        TuitionPlan.objects.filter(studio_id=settings.studio_id).update(
            overdue_reminders_enabled=settings.overdue_email_enabled,
            overdue_template_id=settings.overdue_template_id,
            grace_warning_template_id=settings.grace_warning_template_id,
            grace_expired_template_id=settings.grace_expired_template_id,
            resolved_template_id=settings.resolved_template_id,
        )


class Migration(migrations.Migration):
    dependencies = [("billing", "0009_overdue_and_withdrawal")]

    operations = [
        migrations.AddField(model_name="tuitionplan", name="grace_period_enabled", field=models.BooleanField(default=True)),
        migrations.AddField(model_name="tuitionplan", name="overdue_reminders_enabled", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="tuitionplan", name="overdue_template_id", field=models.PositiveIntegerField(null=True, blank=True)),
        migrations.AddField(model_name="tuitionplan", name="grace_warning_template_id", field=models.PositiveIntegerField(null=True, blank=True)),
        migrations.AddField(model_name="tuitionplan", name="grace_expired_template_id", field=models.PositiveIntegerField(null=True, blank=True)),
        migrations.AddField(model_name="tuitionplan", name="resolved_template_id", field=models.PositiveIntegerField(null=True, blank=True)),
        migrations.RunPython(copy_legacy_settings, migrations.RunPython.noop),
    ]
