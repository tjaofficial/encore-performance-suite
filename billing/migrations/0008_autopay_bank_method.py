from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("billing", "0007_family_autopay_and_test_connect")]

    operations = [
        migrations.AddField(
            model_name="familyautopayprofile",
            name="payment_method_type",
            field=models.CharField(max_length=30, blank=True),
        ),
    ]
