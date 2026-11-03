from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("classes", "0006_repair_registration_window_columns")]
    operations = [migrations.AddField(model_name="class", name="registration_mode", field=models.CharField(max_length=20, choices=[("online", "Online registration"), ("approval", "In-person approval required")], default="online", help_text="Require a studio-issued approval code before online registration."))]
