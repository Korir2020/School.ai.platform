import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("schools", "0058_connect_core")]

    operations = [
        migrations.CreateModel(
            name="ConnectAttachment",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=200)),
                ("content_type", models.CharField(max_length=100)),
                ("size", models.PositiveIntegerField()),
                ("data", models.BinaryField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("post", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="attachments", to="schools.connectpost")),
            ],
        ),
    ]
