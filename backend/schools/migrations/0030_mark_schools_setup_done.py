from django.db import migrations
from django.utils import timezone


def ready(apps, schema_editor):
    School = apps.get_model("schools", "School")
    School.objects.filter(setup_completed_at__isnull=True).update(
        setup_completed_at=timezone.now())


class Migration(migrations.Migration):
    dependencies = [("schools", "0029_school_registration")]
    operations = [migrations.RunPython(ready, migrations.RunPython.noop)]
