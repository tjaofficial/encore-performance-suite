import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("registration_portal", "0005_publicregistrationsession_linked_family_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="publicregistrationsession",
            name="policy_snapshot",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.CreateModel(
            name="RegistrationPolicy",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("policy_key", models.UUIDField(default=uuid.uuid4, editable=False)),
                ("version", models.PositiveIntegerField(default=1)),
                ("is_current", models.BooleanField(default=True)),
                ("title", models.CharField(max_length=180)),
                ("document_type", models.CharField(choices=[("policy", "Policy"), ("agreement", "Agreement"), ("consent", "Consent"), ("waiver", "Waiver / Release")], default="policy", max_length=30)),
                ("content_html", models.TextField()),
                ("acceptance_text", models.CharField(blank=True, max_length=320)),
                ("scope", models.CharField(choices=[("account", "Studio / account registration"), ("all_registrations", "Every registration"), ("specific_classes", "Specific classes")], default="all_registrations", max_length=40)),
                ("is_required", models.BooleanField(default=True)),
                ("requires_signature", models.BooleanField(default=False)),
                ("is_active", models.BooleanField(default=True)),
                ("effective_date", models.DateField(blank=True, null=True)),
                ("display_order", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_registration_policies", to=settings.AUTH_USER_MODEL)),
                ("studio", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="registration_policies", to="studios.studio")),
                ("classes", models.ManyToManyField(blank=True, related_name="registration_policies", to="classes.class")),
            ],
            options={
                "ordering": ["display_order", "title", "pk"],
            },
        ),
        migrations.AddConstraint(
            model_name="registrationpolicy",
            constraint=models.UniqueConstraint(fields=("studio", "policy_key", "version"), name="unique_registration_policy_version"),
        ),
        migrations.CreateModel(
            name="RegistrationPolicyAcceptance",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("policy_key", models.UUIDField()),
                ("policy_version", models.PositiveIntegerField()),
                ("title_snapshot", models.CharField(max_length=180)),
                ("document_type_snapshot", models.CharField(max_length=30)),
                ("content_html_snapshot", models.TextField()),
                ("acceptance_text_snapshot", models.CharField(max_length=320)),
                ("is_required_snapshot", models.BooleanField(default=True)),
                ("requires_signature_snapshot", models.BooleanField(default=False)),
                ("typed_signature", models.CharField(blank=True, max_length=220)),
                ("signer_name", models.CharField(blank=True, max_length=220)),
                ("signer_email", models.EmailField(blank=True, max_length=254)),
                ("selected_class_ids_snapshot", models.JSONField(blank=True, default=list)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.CharField(blank=True, max_length=1000)),
                ("accepted_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("linked_family", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="registration_policy_acceptances", to="families.family")),
                ("linked_user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="registration_policy_acceptances", to=settings.AUTH_USER_MODEL)),
                ("policy", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="acceptances", to="registration_portal.registrationpolicy")),
                ("registration_session", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="policy_acceptances", to="registration_portal.publicregistrationsession")),
            ],
            options={
                "ordering": ["accepted_at", "pk"],
            },
        ),
        migrations.AddConstraint(
            model_name="registrationpolicyacceptance",
            constraint=models.UniqueConstraint(fields=("registration_session", "policy"), name="unique_registration_policy_acceptance"),
        ),
    ]
