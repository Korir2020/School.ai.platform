import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("schools", "0070_setup_types_and_name_constraints"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="OffsiteBackupRun",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("status", models.CharField(choices=[("queued", "Queued"), ("running", "Running"), ("succeeded", "Succeeded"), ("failed", "Failed")], db_index=True, default="queued", max_length=12)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("lease_token", models.UUIDField(blank=True, null=True)),
                ("lease_expires_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("retry_after", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("attempts", models.PositiveSmallIntegerField(default=0)),
                ("archive_keys", models.JSONField(blank=True, default=dict)),
                ("manifest_key", models.CharField(blank=True, max_length=500)),
                ("error", models.TextField(blank=True)),
                ("result", models.JSONField(blank=True, default=dict)),
                ("requested_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="offsite_backup_runs", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="OfflineMarkOperation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("operation_id", models.UUIDField()),
                ("payload_sha256", models.CharField(max_length=64)),
                ("response", models.JSONField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="offline_mark_operations", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddConstraint(
            model_name="offlinemarkoperation",
            constraint=models.UniqueConstraint(fields=("user", "operation_id"), name="unique_user_offline_mark_operation"),
        ),
        migrations.AddIndex(
            model_name="offlinemarkoperation",
            index=models.Index(fields=["user", "created_at"], name="offline_mark_user_created_idx"),
        ),
    ]
