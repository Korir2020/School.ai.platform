from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def backfill_subject_registrations(apps, schema_editor):
    Enrollment = apps.get_model("schools", "Enrollment")
    Performance = apps.get_model("schools", "Performance")
    SubjectRegistration = apps.get_model("schools", "SubjectRegistration")
    TeacherAssignment = apps.get_model("schools", "TeacherAssignment")
    db = schema_editor.connection.alias

    batch = []

    def flush():
        if batch:
            SubjectRegistration.objects.using(db).bulk_create(
                batch, ignore_conflicts=True, batch_size=1000,
            )
            batch.clear()

    # Preserve prior official and in-progress marks as valid registrations.
    for performance in Performance.objects.using(db).values(
        "student_id", "academic_year_id", "subject_id", "student__school_id",
        "subject__school_id",
    ).iterator(chunk_size=1000):
        if performance["student__school_id"] == performance["subject__school_id"]:
            batch.append(SubjectRegistration(
                student_id=performance["student_id"],
                academic_year_id=performance["academic_year_id"],
                subject_id=performance["subject_id"],
                category="compulsory",
            ))
            if len(batch) >= 1000:
                flush()
    flush()

    # Seed current academic-year cohorts from existing class/stream assignments.
    for enrollment in Enrollment.objects.using(db).filter(
        is_active=True, academic_year__is_active=True, stream_id__isnull=False,
    ).values(
        "student_id", "academic_year_id", "stream_id", "student__school_id",
    ).iterator(chunk_size=1000):
        subject_ids = TeacherAssignment.objects.using(db).filter(
            school_id=enrollment["student__school_id"],
            stream_id=enrollment["stream_id"],
        ).values_list("subject_id", flat=True).iterator(chunk_size=1000)
        for subject_id in subject_ids:
            batch.append(SubjectRegistration(
                student_id=enrollment["student_id"],
                academic_year_id=enrollment["academic_year_id"],
                subject_id=subject_id,
                category="compulsory",
            ))
            if len(batch) >= 1000:
                flush()

    flush()


class Migration(migrations.Migration):
    dependencies = [
        ("schools", "0064_announcements_alerts"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SubjectRegistration",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("category", models.CharField(choices=[("compulsory", "Compulsory"), ("optional", "Optional")], max_length=12)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("academic_year", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="subject_registrations", to="schools.academicyear")),
                ("registered_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="subject_registrations", to="schools.student")),
                ("subject", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="registrations", to="schools.subject")),
            ],
            options={"ordering": ["subject__name", "id"]},
        ),
        migrations.AddConstraint(
            model_name="subjectregistration",
            constraint=models.UniqueConstraint(fields=("student", "academic_year", "subject"), name="unique_student_year_subject_registration"),
        ),
        migrations.AddIndex(
            model_name="subjectregistration",
            index=models.Index(fields=["academic_year", "student"], name="subreg_year_student_idx"),
        ),
        migrations.RunPython(backfill_subject_registrations, migrations.RunPython.noop),
    ]
