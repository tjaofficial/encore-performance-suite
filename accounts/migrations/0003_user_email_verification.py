from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_dashboardpreference"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="email_verification_required",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="user",
            name="email_verified_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="user",
            name="email_verification_token",
            field=models.UUIDField(blank=True, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="user",
            name="email_verification_sent_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
