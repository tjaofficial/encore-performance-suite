from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [ ("resources", "0003_classresource_dance"), migrations.swappable_dependency(settings.AUTH_USER_MODEL) ]
    operations = [
        migrations.AddField(model_name="classresource", name="approval_status", field=models.CharField(max_length=12, db_index=True, choices=[("approved","Approved"),("pending","Pending Approval"),("rejected","Rejected"),("replaced","Replaced")], default="approved")),
        migrations.AddField(model_name="classresource", name="reviewed_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="classresource", name="review_comment", field=models.TextField(blank=True)),
        migrations.AddField(model_name="classresource", name="reviewed_by", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reviewed_dance_music", to=settings.AUTH_USER_MODEL)),
    ]
