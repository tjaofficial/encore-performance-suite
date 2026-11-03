from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("studios", "0009_studiomembership_onboarding_tour")]

    operations = [
        migrations.AddField(
            model_name="studiosettings",
            name="parent_sidebar_color",
            field=models.CharField(default="#FFFFFF", max_length=7),
        ),
        migrations.AddField(
            model_name="studiosettings",
            name="parent_logo_header_color",
            field=models.CharField(default="#E9EFFF", max_length=7),
        ),
    ]
