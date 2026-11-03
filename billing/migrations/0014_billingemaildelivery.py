from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [('billing', '0013_importedfamilytuitionreview')]
    operations = [migrations.CreateModel(name='BillingEmailDelivery',fields=[
        ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
        ('event_key',models.CharField(max_length=200)),
        ('event_type',models.CharField(max_length=40)),
        ('recipient',models.EmailField(max_length=254)),
        ('subject',models.CharField(max_length=255)),
        ('body',models.TextField()),
        ('status',models.CharField(choices=[('pending','Pending'),('sending','Sending'),('sent','Sent'),('failed','Failed')],default='pending',max_length=16)),
        ('provider_message_id',models.CharField(blank=True,max_length=255)),
        ('error',models.TextField(blank=True)),
        ('attempts',models.PositiveIntegerField(default=0)),
        ('created_at',models.DateTimeField(auto_now_add=True)),
        ('sent_at',models.DateTimeField(blank=True,null=True)),
        ('account',models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name='email_deliveries',to='billing.familyaccount')),
    ],options={'ordering':['-created_at']},),
    migrations.AddConstraint(model_name='billingemaildelivery',constraint=models.UniqueConstraint(fields=('account','event_key','recipient'),name='unique_billing_email_delivery'))]
