from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [("performance", "0011_drawingboardwithdrawalsnapshot")]
    operations = [migrations.CreateModel(name="StageLightingTemplate", fields=[
        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
        ("name", models.CharField(max_length=160)),
        ("description", models.TextField(blank=True)),
        ("stage_drawings", models.JSONField(default=list, blank=True)),
        ("show_offstage_wings", models.BooleanField(default=False)),
        ("apron_stage_grid", models.BooleanField(default=False)),
        ("fixtures", models.JSONField(default=list, blank=True)),
        ("cues", models.JSONField(default=list, blank=True)),
        ("created_at", models.DateTimeField(auto_now_add=True)),
        ("updated_at", models.DateTimeField(auto_now=True)),
        ("studio", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="stage_lighting_templates", to="studios.studio")),
    ], options={"ordering": ["name", "id"]}),
    migrations.AddConstraint(model_name="stagelightingtemplate",constraint=models.UniqueConstraint(fields=("studio", "name"),name="unique_studio_stage_lighting_template")),]
