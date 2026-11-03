from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [("billing", "0014_billingemaildelivery"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(name="PaymentRefund", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("amount", models.DecimalField(decimal_places=2, max_digits=10)),
            ("status", models.CharField(max_length=20, choices=[("processing", "Processing"), ("pending", "Pending at Stripe"), ("succeeded", "Succeeded"), ("failed", "Failed"), ("canceled", "Canceled")], default="processing")),
            ("reason", models.CharField(max_length=30)),
            ("notes", models.TextField()),
            ("stripe_refund_id", models.CharField(blank=True, max_length=255, null=True, unique=True)),
            ("stripe_account_id", models.CharField(max_length=255)),
            ("idempotency_key", models.CharField(max_length=100, unique=True)),
            ("last_error", models.TextField(blank=True)),
            ("ledger_applied", models.BooleanField(default=False)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("updated_at", models.DateTimeField(auto_now=True)),
            ("charge", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="refunds", to="billing.charge")),
            ("payment", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="refunds", to="billing.payment")),
            ("requested_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
        ], options={"ordering": ["-created_at"]})
    ]
