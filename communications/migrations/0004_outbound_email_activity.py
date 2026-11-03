from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [("communications", "0003_emailcampaign_recipient_selection_and_more")]
    operations = [
        migrations.CreateModel(name="OutboundEmailLog", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("to_addresses", models.JSONField(default=list)),
            ("cc_addresses", models.JSONField(blank=True, default=list)),
            ("bcc_addresses", models.JSONField(blank=True, default=list)),
            ("sender", models.CharField(max_length=320)),
            ("reply_to_addresses", models.JSONField(blank=True, default=list)),
            ("subject", models.TextField()),
            ("text_body", models.TextField(blank=True)),
            ("html_body", models.TextField(blank=True)),
            ("category", models.CharField(blank=True, max_length=80)),
            ("source", models.CharField(blank=True, max_length=80)),
            ("provider_message_id", models.CharField(blank=True, db_index=True, max_length=255)),
            ("status", models.CharField(db_index=True, default="queued", max_length=30)),
            ("error", models.TextField(blank=True)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("accepted_at", models.DateTimeField(blank=True, null=True)),
            ("delivered_at", models.DateTimeField(blank=True, null=True)),
            ("last_event_at", models.DateTimeField(blank=True, null=True)),
            ("studio", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="outbound_email_logs", to="studios.studio")),
        ], options={"ordering": ["-created_at"]}),
        migrations.CreateModel(name="OutboundEmailEvent", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("event_type", models.CharField(max_length=40)),
            ("event_key", models.CharField(max_length=255, unique=True)),
            ("occurred_at", models.DateTimeField()),
            ("detail", models.JSONField(blank=True, default=dict)),
            ("email", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="delivery_events", to="communications.outboundemaillog")),
        ], options={"ordering": ["-occurred_at"]}),
        migrations.AddIndex(model_name="outboundemaillog", index=models.Index(fields=["studio", "-created_at"], name="comm_out_studio_49a713_idx")),
    ]
