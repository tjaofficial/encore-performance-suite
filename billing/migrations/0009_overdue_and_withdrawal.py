from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion



def ensure_existing_tuition_tables(apps, schema_editor):
    """Create *missing* legacy tuition tables without touching existing records.

    A previous version shipped these models without corresponding migration
    state. Existing installations may already have physical tables created
    outside this migration history. Never drop or overwrite those tables.
    """
    for name in ("StudioTuitionSettings", "TuitionRateTier"):
        model = apps.get_model("billing", name)
        if model._meta.db_table not in schema_editor.connection.introspection.table_names():
            schema_editor.create_model(model)

class Migration(migrations.Migration):
    dependencies = [("billing", "0008_autopay_bank_method"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        # These two models exist in application code and may already have
        # physical tables, but were omitted from migrations 0001–0008.
        # Restore historical *state* without blindly recreating tables.
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="StudioTuitionSettings",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("studio", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="tuition_settings", to="studios.studio")),
                        ("pricing_mode", models.CharField(max_length=20, choices=[("per_class", "Per-Class Tuition"), ("studio_wide", "Studio-Wide Tuition")], default="per_class")),
                        ("studio_wide_method", models.CharField(max_length=20, choices=[("flat_hourly", "Flat Hourly Rate"), ("tiered_hourly", "Tiered Hourly Rates")], default="tiered_hourly")),
                        ("flat_hourly_rate", models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)),
                        ("additional_hour_rate", models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)),
                        ("family_monthly_cap", models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)),
                        ("default_tuition_plan", models.ForeignKey(to="billing.tuitionplan", on_delete=django.db.models.deletion.SET_NULL, null=True, blank=True, related_name="studio_tuition_defaults")),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                    ],
                ),
                migrations.CreateModel(
                    name="TuitionRateTier",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("hour_number", models.PositiveIntegerField()),
                        ("hourly_rate", models.DecimalField(max_digits=10, decimal_places=2)),
                        ("settings", models.ForeignKey(to="billing.studiotuitionsettings", on_delete=django.db.models.deletion.CASCADE, related_name="rate_tiers")),
                    ],
                    options={
                        "ordering": ["hour_number"],
                        "constraints": [models.UniqueConstraint(fields=("settings", "hour_number"), name="unique_tuition_hour_tier_per_studio")],
                    },
                ),
            ],
            database_operations=[],
        ),
        migrations.RunPython(ensure_existing_tuition_tables, migrations.RunPython.noop),
        migrations.AddField(model_name="studiotuitionsettings", name="overdue_grace_days", field=models.PositiveSmallIntegerField(default=7, help_text="Calendar days after the charge due date before an attendance review is eligible.")),
        migrations.AddField(model_name="studiotuitionsettings", name="overdue_email_enabled", field=models.BooleanField(default=False, help_text="Off by default: enable after reviewing email templates.")),
        migrations.AddField(model_name="studiotuitionsettings", name="overdue_template_id", field=models.PositiveIntegerField(null=True, blank=True, help_text="Optional ID of this studio's EmailTemplate for overdue notices.")),
        migrations.AddField(model_name="studiotuitionsettings", name="grace_warning_template_id", field=models.PositiveIntegerField(null=True, blank=True)),
        migrations.AddField(model_name="studiotuitionsettings", name="grace_expired_template_id", field=models.PositiveIntegerField(null=True, blank=True)),
        migrations.AddField(model_name="studiotuitionsettings", name="resolved_template_id", field=models.PositiveIntegerField(null=True, blank=True)),
        migrations.AddField(model_name="studiotuitionsettings", name="attendance_review_enabled", field=models.BooleanField(default=False, help_text="Flag overdue accounts for staff review only; never automatically mark a student absent.")),
        migrations.CreateModel(name="BillingNoticeDelivery", fields=[("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),("event",models.CharField(max_length=40)),("status",models.CharField(choices=[("pending","Pending"),("sent","Sent"),("failed","Failed")], default="pending",max_length=12)),("error",models.TextField(blank=True)),("sent_at",models.DateTimeField(blank=True,null=True)),("created_at",models.DateTimeField(auto_now_add=True)),("charge",models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name="billing_notices",to="billing.charge"))],options={"constraints":[models.UniqueConstraint(fields=("charge","event"),name="billing_notice_per_charge_event")]}),
        migrations.CreateModel(name="FamilyBillingHold",fields=[("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),("status",models.CharField(choices=[("review","Needs review"),("active","Approved review flag (not enforced)"),("released","Released")],default="review",max_length=12)),("reason",models.TextField(blank=True)),("reviewed_at",models.DateTimeField(null=True,blank=True)),("created_at",models.DateTimeField(auto_now_add=True)),("updated_at",models.DateTimeField(auto_now=True)),("account",models.OneToOneField(on_delete=django.db.models.deletion.CASCADE,related_name="billing_hold",to="billing.familyaccount")),("reviewed_by",models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.SET_NULL,to=settings.AUTH_USER_MODEL))]),
        migrations.CreateModel(name="FamilyWithdrawalRequest",fields=[("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),("reason",models.TextField(blank=True)),("status",models.CharField(choices=[("pending","Pending studio review"),("approved","Approved"),("rejected","Rejected")],default="pending",max_length=12)),("reviewed_at",models.DateTimeField(blank=True,null=True)),("created_at",models.DateTimeField(auto_now_add=True)),("account",models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name="withdrawal_requests",to="billing.familyaccount")),("enrollment",models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name="withdrawal_requests",to="enrollments.enrollment")),("requested_by",models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name="requested_withdrawals",to=settings.AUTH_USER_MODEL)),("reviewed_by",models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.SET_NULL,related_name="reviewed_withdrawals",to=settings.AUTH_USER_MODEL))],options={"ordering":["-created_at"]}),
    ]
