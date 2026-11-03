from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("instructors", "0003_payroll_foundation"),
    ]

    operations = [
        migrations.AddField(
            model_name="payrollsettings",
            name="pay_period_anchor_date",
            field=models.DateField(
                blank=True,
                help_text=(
                    "A known first day of a weekly or biweekly pay period. "
                    "Monthly and semi-monthly schedules do not use this field."
                ),
                null=True,
            ),
        ),
    ]
