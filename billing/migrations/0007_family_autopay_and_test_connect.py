from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("billing", "0006_studiosignupintent_signup_emails"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.AddField(model_name="studiosubscription", name="stripe_test_connected_account_id", field=models.CharField(max_length=255, blank=True)),
        migrations.CreateModel(name="FamilyAutoPayProfile", fields=[
            ("id", models.BigAutoField(primary_key=True, serialize=False)),
            ("mode", models.CharField(max_length=4, choices=[("test", "Test"), ("live", "Live")])),
            ("connected_account_id", models.CharField(max_length=255)),
            ("stripe_customer_id", models.CharField(max_length=255, blank=True)),
            ("stripe_payment_method_id", models.CharField(max_length=255, blank=True)),
            ("card_brand", models.CharField(max_length=30, blank=True)),
            ("card_last4", models.CharField(max_length=4, blank=True)),
            ("enabled_at", models.DateTimeField(null=True, blank=True)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("updated_at", models.DateTimeField(auto_now=True)),
            ("account", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="autopay_profiles", to="billing.familyaccount")),
            ("consent_user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
        ], options={"constraints": [models.UniqueConstraint(fields=("account", "mode"), name="unique_family_autopay_mode")]}),
        migrations.CreateModel(name="FamilyAutoPayAttempt", fields=[
            ("id", models.BigAutoField(primary_key=True, serialize=False)),
            ("stripe_payment_intent_id", models.CharField(max_length=255, blank=True)),
            ("status", models.CharField(max_length=30, default="pending")),
            ("error_message", models.TextField(blank=True)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("updated_at", models.DateTimeField(auto_now=True)),
            ("charge", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="autopay_attempt", to="billing.charge")),
            ("profile", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="attempts", to="billing.familyautopayprofile")),
        ]),
    ]
