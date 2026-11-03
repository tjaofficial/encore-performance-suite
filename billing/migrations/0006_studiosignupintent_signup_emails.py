from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0005_remove_payment_modes_and_add_terms_acceptance"),
    ]

    operations = [
        migrations.AddField(
            model_name="studiosignupintent",
            name="purchase_confirmation_sent_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="studiosignupintent",
            name="welcome_email_sent_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
