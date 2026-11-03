import uuid

from django.db import migrations, models


def populate_activation_tokens(apps, schema_editor):
    Instructor = apps.get_model("instructors", "Instructor")

    for instructor in Instructor.objects.filter(
        activation_token__isnull=True
    ).iterator():
        instructor.activation_token = uuid.uuid4()
        instructor.save(
            update_fields=["activation_token"]
        )


class Migration(migrations.Migration):

    dependencies = [
        ("instructors", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="instructor",
            name="activation_token",
            field=models.UUIDField(
                blank=True,
                editable=False,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="instructor",
            name="activation_sent_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="instructor",
            name="activation_expires_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="instructor",
            name="claimed_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="instructor",
            name="profile_verified_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="instructor",
            name="availability_completed_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
            ),
        ),
        migrations.RunPython(
            populate_activation_tokens,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="instructor",
            name="activation_token",
            field=models.UUIDField(
                default=uuid.uuid4,
                editable=False,
                unique=True,
            ),
        ),
    ]
