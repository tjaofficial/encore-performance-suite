from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [('billing', '0012_family_billing_action'), ('studios', '0009_studiomembership_onboarding_tour'), ('families', '0001_initial'), ('classes', '0001_initial')]
    operations = [migrations.CreateModel(name='ImportedFamilyTuitionReview', fields=[
        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
        ('amount_override', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
        ('updated_at', models.DateTimeField(auto_now=True)),
        ('studio', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='studios.studio')),
        ('family', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='families.family')),
        ('season', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='classes.season')),
    ]), migrations.AddConstraint(model_name='importedfamilytuitionreview', constraint=models.UniqueConstraint(fields=('studio', 'family', 'season'), name='unique_imported_family_tuition_review'))]
