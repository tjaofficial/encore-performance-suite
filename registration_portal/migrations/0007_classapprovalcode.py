from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [("registration_portal", "0006_registration_policies_and_acceptances"), ("classes", "0007_class_registration_mode"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [migrations.CreateModel(name="ClassApprovalCode", fields=[
        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
        ("parent_email", models.EmailField(max_length=254)),
        ("code_hash", models.CharField(max_length=128, unique=True)),
        ("expires_at", models.DateTimeField()),
        ("claimed_student_key", models.CharField(blank=True, max_length=100)),
        ("used_at", models.DateTimeField(blank=True, null=True)),
        ("revoked_at", models.DateTimeField(blank=True, null=True)),
        ("created_at", models.DateTimeField(auto_now_add=True)),
        ("class_instance", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="approval_codes", to="classes.class")),
        ("studio", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="class_approval_codes", to="studios.studio")),
        ("claimed_session", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="registration_portal.publicregistrationsession")),
        ("issued_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
    ], options={"ordering": ["-created_at"]})]
