from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


def zero_to_one(apps, schema_editor):
    # Owner rule: a valid mark is 1-100 and 1 = absent.
    # Old 0 marks (practice data only) become 1.
    P = apps.get_model("schools", "Performance")
    P.objects.filter(marks__lt=1).update(marks=1)


class Migration(migrations.Migration):

    dependencies = [
        ("schools", "0025_schooladminprofile_is_deputy"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="performance", name="performance_marks_0_100",
        ),
        migrations.RunPython(zero_to_one, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="performance",
            name="marks",
            field=models.DecimalField(
                decimal_places=2, max_digits=5,
                validators=[MinValueValidator(1), MaxValueValidator(100)],
            ),
        ),
        migrations.AddConstraint(
            model_name="performance",
            constraint=models.CheckConstraint(
                condition=models.Q(("marks__gte", 1), ("marks__lte", 100)),
                name="performance_marks_1_100",
            ),
        ),
    ]
