from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    dependencies = [("learning", "0009_learningschoolsettings_learn_school_age_min_plausible")]
    operations = [
        migrations.CreateModel(
            name="LearningMotivationSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("enabled", models.BooleanField(default=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("profile", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="motivation_settings", to="learning.learningprofile")),
            ],
        ),
        migrations.CreateModel(
            name="LearningOfflinePackage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("package_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("device_id", models.CharField(max_length=128)),
                ("manifest", models.JSONField(default=dict)),
                ("issued_at", models.DateTimeField(auto_now_add=True)),
                ("expires_at", models.DateTimeField()),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("last_sync_at", models.DateTimeField(blank=True, null=True)),
                ("profile", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="offline_packages", to="learning.learningprofile")),
            ],
            options={"ordering": ["-issued_at"], "indexes": [models.Index(fields=["profile", "expires_at"], name="learn_offline_profile_exp_idx")]},
        ),
        migrations.CreateModel(
            name="LearningOfflineOperation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("operation_id", models.UUIDField()),
                ("event_type", models.CharField(max_length=12)),
                ("payload", models.JSONField(default=dict)),
                ("state", models.CharField(choices=[("synced", "Synced"), ("conflict", "Conflict")], max_length=10)),
                ("conflict_code", models.CharField(blank=True, default="", max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("synced_at", models.DateTimeField(blank=True, null=True)),
                ("package", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="operations", to="learning.learningofflinepackage")),
            ],
            options={"indexes": [models.Index(fields=["package", "state"], name="learn_offline_op_state_idx")]},
        ),
        migrations.AddConstraint(
            model_name="learningofflineoperation",
            constraint=models.UniqueConstraint(fields=("package", "operation_id"), name="learn_offline_op_unique"),
        ),
    ]
