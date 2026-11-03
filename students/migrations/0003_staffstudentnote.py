from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [('students','0002_alter_student_gender'), ('classes','0007_class_registration_mode'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [migrations.CreateModel(name='StaffStudentNote', fields=[
        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
        ('text', models.TextField(blank=True, default='')),
        ('updated_at', models.DateTimeField(auto_now=True)),
        ('class_instance', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='classes.class')),
        ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='staff_notes', to='students.student')),
        ('studio', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='studios.studio')),
        ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
    ], options={'constraints': [
        models.UniqueConstraint(fields=('student','class_instance'), condition=models.Q(class_instance__isnull=False), name='unique_student_class_staff_note'),
        models.UniqueConstraint(fields=('student',), condition=models.Q(class_instance__isnull=True), name='unique_student_general_staff_note'),
    ]})]
