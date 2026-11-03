from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        (
            "billing",
            "0004_studiosubscription_stripe_connect_charges_enabled_and_more",
        ),
    ]

    operations = [
        migrations.RemoveField(
            model_name="studiosubscription",
            name="payment_mode",
        ),
        migrations.RemoveField(
            model_name="studiosubscription",
            name="pending_payment_mode",
        ),
        migrations.RemoveField(
            model_name="studiosignupintent",
            name="payment_mode",
        ),
        migrations.AddField(
            model_name="studiosignupintent",
            name="terms_version",
            field=models.CharField(default="2026-10-02", max_length=20),
        ),
        migrations.AddField(
            model_name="studiosignupintent",
            name="terms_accepted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
