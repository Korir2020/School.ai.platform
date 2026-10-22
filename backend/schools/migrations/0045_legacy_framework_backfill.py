from django.db import migrations

LEGACY = "legacy_untracked"


def mark_legacy(apps, schema_editor):
    Exam = apps.get_model("schools", "Exam")
    Exam.objects.filter(status="published", framework_key__isnull=True).update(framework_key=LEGACY)


def unmark_legacy(apps, schema_editor):
    Exam = apps.get_model("schools", "Exam")
    Exam.objects.filter(framework_key=LEGACY, framework_version__isnull=True).update(framework_key=None)


class Migration(migrations.Migration):

    dependencies = [
        ('schools', '0044_framework_settings'),
    ]

    operations = [
        migrations.RunPython(mark_legacy, unmark_legacy),
    ]
