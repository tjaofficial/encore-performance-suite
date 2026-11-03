from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [("billing", "0011_individual_overdue_notice_controls"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [migrations.CreateModel(name="FamilyBillingAction", fields=[
        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
        ("action", models.CharField(max_length=40)),
        ("reason", models.TextField()),
        ("details", models.JSONField(blank=True, default=dict)),
        ("created_at", models.DateTimeField(auto_now_add=True)),
        ("account", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="billing_actions", to="billing.familyaccount")),
        ("charge", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="review_actions", to="billing.charge")),
        ("performed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
    ], options={"ordering": ["-created_at"]})]
