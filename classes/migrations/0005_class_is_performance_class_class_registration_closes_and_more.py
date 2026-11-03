from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("classes", "0004_classmeeting_room"),
        ("studios", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="class",
            name="min_age",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=5,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="class",
            name="max_age",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=5,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="class",
            name="is_performance_class",
            field=models.BooleanField(
                blank=True,
                default=None,
                help_text=(
                    "Performance class, non-performance class, or unknown. "
                    "Unknown is useful while imported data is being reviewed."
                ),
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="class",
            name="registration_opens",
            field=models.DateField(
                blank=True,
                help_text=(
                    "Optional class-specific registration opening date. "
                    "Leave blank to rely on the studio/season registration setup."
                ),
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="class",
            name="registration_closes",
            field=models.DateField(
                blank=True,
                help_text=(
                    "Optional class-specific registration closing date. "
                    "Leave blank to rely on the studio/season registration setup."
                ),
                null=True,
            ),
        ),
        migrations.CreateModel(
            name="ClassLevel",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "number",
                    models.PositiveSmallIntegerField(),
                ),
                (
                    "name",
                    models.CharField(
                        max_length=100,
                    ),
                ),
                (
                    "description",
                    models.TextField(
                        blank=True,
                    ),
                ),
                (
                    "aliases",
                    models.JSONField(
                        blank=True,
                        default=list,
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        default=True,
                    ),
                ),
                (
                    "studio",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="class_levels",
                        to="studios.studio",
                    ),
                ),
            ],
            options={
                "ordering": [
                    "number",
                    "name",
                ],
            },
        ),
        migrations.AddField(
            model_name="class",
            name="level",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="classes",
                to="classes.classlevel",
            ),
        ),
        migrations.AddConstraint(
            model_name="classlevel",
            constraint=models.UniqueConstraint(
                fields=(
                    "studio",
                    "number",
                ),
                name="unique_class_level_number_per_studio",
            ),
        ),
        migrations.AddConstraint(
            model_name="classlevel",
            constraint=models.UniqueConstraint(
                fields=(
                    "studio",
                    "name",
                ),
                name="unique_class_level_name_per_studio",
            ),
        ),
    ]