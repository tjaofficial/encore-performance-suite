from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [("performance", "0010_drawingboard_apron_stage_grid_and_more")]
    operations = [
        migrations.CreateModel(
            name="DrawingBoardWithdrawalSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("enrollment_id", models.PositiveBigIntegerField(db_index=True)),
                ("student_id", models.PositiveBigIntegerField(db_index=True)),
                ("student_name", models.CharField(max_length=250)),
                ("reason", models.CharField(default="withdrawal", max_length=50)),
                ("recorded_at", models.DateTimeField(auto_now_add=True)),
                ("snapshot", models.JSONField(default=dict)),
                ("board", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="withdrawal_snapshots", to="performance.drawingboard")),
            ],
            options={"ordering": ["-recorded_at", "-id"]},
        ),
        migrations.AddConstraint(
            model_name="drawingboardwithdrawalsnapshot",
            constraint=models.UniqueConstraint(fields=("board", "enrollment_id"), name="unique_board_withdrawal_snapshot"),
        ),
    ]
