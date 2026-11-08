from django.db import migrations, models
from django.db.models.functions import Lower, Trim


TYPE_MAP = {
    # Values used by the original school-registration choices and the
    # aliases accepted by the setup/profile UI over time.
    "primary": "primary",
    "primary school": "primary",
    "elementary": "primary",
    "elementary school": "primary",
    "junior": "junior",
    "junior school": "junior",
    "middle school": "junior",
    "combined": "combined",
    "combined / other": "combined",
    "combined (junior and primary)": "combined",
    "senior": "senior",
    "senior school": "senior",
    "secondary": "senior",
    "secondary school": "senior",
    "senior / secondary": "senior",
}


def normalize(value):
    return str(value or "").strip().lower()


def _trimmed(value):
    return str(value or "").strip()


def _key(value):
    return _trimmed(value).lower()


def _with_suffix(base, label, max_length):
    """Keep the disambiguator visible while respecting the field length."""
    label = _trimmed(label) or "level"
    suffix = f" ({label})"
    if len(suffix) >= max_length:
        label = label[: max(1, max_length - 5)].rstrip()
        suffix = f" ({label})"
    head = _trimmed(base)[: max(1, max_length - len(suffix))].rstrip()
    return (head + suffix)[:max_length]


def _unique_name(base, label, max_length, used):
    candidate = _trimmed(base) or "Item"
    if _key(candidate) not in used:
        return candidate[:max_length]
    number = 1
    while True:
        numbered = label if number == 1 else f"{label} {number}"
        candidate = _with_suffix(base, numbered, max_length)
        if _key(candidate) not in used:
            return candidate
        number += 1


def map_school_types(apps, schema_editor):
    for model_name in ("School", "SchoolRegistration"):
        model = apps.get_model("schools", model_name)
        for row in model.objects.exclude(school_type="").iterator():
            mapped = TYPE_MAP.get(normalize(row.school_type))
            # Unknown legacy values are left untouched. In particular, this
            # migration never guesses or invents a ministry code.
            if mapped and row.school_type != mapped:
                row.school_type = mapped
                row.save(update_fields=["school_type"])


def repair_stream_names(apps, schema_editor):
    Stream = apps.get_model("schools", "Stream")
    used_by_school = {}
    rows = Stream.objects.select_related("class_level").order_by("school_id", "id")
    for row in rows.iterator():
        used = used_by_school.setdefault(row.school_id, set())
        base = _trimmed(row.name) or f"Stream {row.id}"
        level = getattr(row, "class_level", None)
        label = _trimmed(getattr(level, "name", "")) or f"Level {row.class_level_id}"
        name = _unique_name(base, label, 50, used)
        if row.name != name:
            row.name = name
            row.save(update_fields=["name"])
        used.add(_key(name))


def repair_subject_names(apps, schema_editor):
    Subject = apps.get_model("schools", "Subject")
    used_by_school = {}
    rows = Subject.objects.order_by("school_id", "id")
    for row in rows.iterator():
        used = used_by_school.setdefault(row.school_id, set())
        base = _trimmed(row.name) or f"Subject {row.id}"
        name = _unique_name(base, "duplicate", 100, used)
        if row.name != name:
            row.name = name
            row.save(update_fields=["name"])
        used.add(_key(name))


def prepare_existing_data(apps, schema_editor):
    repair_stream_names(apps, schema_editor)
    repair_subject_names(apps, schema_editor)


def unmap_school_types(apps, schema_editor):
    # Canonical values are intentionally retained on rollback so a rollback
    # cannot silently turn a Senior school back into the ambiguous "secondary".
    return None


class Migration(migrations.Migration):
    dependencies = [
        ("schools", "0069_enrollment_pathway"),
    ]

    operations = [
        migrations.AlterField(
            model_name="school",
            name="school_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("primary", "Primary school"),
                    ("junior", "Junior school"),
                    ("combined", "Combined (junior and primary)"),
                    ("senior", "Senior school"),
                ],
                max_length=30,
            ),
        ),
        migrations.AlterField(
            model_name="schoolregistration",
            name="school_type",
            field=models.CharField(
                choices=[
                    ("primary", "Primary school"),
                    ("junior", "Junior school"),
                    ("combined", "Combined (junior and primary)"),
                    ("senior", "Senior school"),
                ],
                max_length=30,
            ),
        ),
        migrations.RunPython(map_school_types, unmap_school_types),
        migrations.RunPython(prepare_existing_data, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="stream",
            constraint=models.UniqueConstraint(
                Lower(Trim("name")), "school", name="unique_stream_name_per_school",
            ),
        ),
        migrations.AddConstraint(
            model_name="subject",
            constraint=models.UniqueConstraint(
                Lower(Trim("name")), "school", name="unique_subject_name_per_school",
            ),
        ),
    ]
