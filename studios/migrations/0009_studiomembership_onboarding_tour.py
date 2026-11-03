from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        (
            "studios",
            "0008_studiosettings_measurement_unit_and_more",
        ),
    ]

    operations = [
        migrations.AddField(
            model_name="studiomembership",
            name="onboarding_tour_status",
            field=models.CharField(
                choices=[
                    ("not_started", "Not Started"),
                    ("in_progress", "In Progress"),
                    ("skipped", "Skipped"),
                    ("completed", "Completed"),
                ],
                default="completed",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="studiomembership",
            name="onboarding_tour_step",
            field=models.PositiveSmallIntegerField(default=0),
        ),
    ]
