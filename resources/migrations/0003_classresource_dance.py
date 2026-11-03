from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("resources", "0002_classresource_artist_classresource_duration_seconds"), ("performance", "0011_drawingboardwithdrawalsnapshot")]

    operations = [
        migrations.AddField(
            model_name="classresource",
            name="dance",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="linked_resources", to="performance.choreographyplan", help_text="Optional dance this resource belongs to."),
        ),
    ]
