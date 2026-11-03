from django.db import migrations, models


def preserve_existing_choices(apps, schema_editor):
    Policy = apps.get_model("billing", "TuitionPlan")
    for policy in Policy.objects.all().iterator():
        enabled = policy.overdue_reminders_enabled
        Policy.objects.filter(pk=policy.pk).update(
            overdue_notice_enabled=enabled,
            grace_warning_notice_enabled=enabled,
            resolved_notice_enabled=True,
        )


class Migration(migrations.Migration):
    dependencies = [("billing", "0010_policy_overdue_notifications")]
    operations = [
        migrations.AddField(model_name="tuitionplan", name="overdue_notice_enabled", field=models.BooleanField(default=True)),
        migrations.AddField(model_name="tuitionplan", name="grace_warning_notice_enabled", field=models.BooleanField(default=True)),
        migrations.AddField(model_name="tuitionplan", name="resolved_notice_enabled", field=models.BooleanField(default=True)),
        migrations.RunPython(preserve_existing_choices, migrations.RunPython.noop),
    ]
