from django.core.management.base import BaseCommand
from django.db import transaction

from schools.models import ClassLevel, Curriculum, SubjectDefinition

LEVELS = {
    7: "Lower Secondary Stage 7", 8: "Lower Secondary Stage 8",
    9: "Lower Secondary Stage 9", 10: "IGCSE Year 10", 11: "IGCSE Year 11",
}

# Cambridge Lower Secondary subjects missing from the original catalogue.
NEW_SUBJECTS = {"COMPUTING": "Computing", "ICTSTART": "ICT Starters"}

# Cambridge IGCSE subjects (Years 10-11) missing from the original catalogue.
NEW_IGCSE_SUBJECTS = {
    "ADDMATH": "Mathematics - Additional",
    "COORDSCI": "Sciences - Co-ordinated (Double Award)",
    "LITENG": "English - Literature in English",
    "GP": "Global Perspectives",
}


class Command(BaseCommand):
    help = "Add missing Cambridge Lower Secondary subjects (safe to re-run)."

    @transaction.atomic
    def handle(self, *args, **options):
        cur, _ = Curriculum.objects.get_or_create(
            code="CAMBRIDGE", defaults={"name": "Cambridge International"}
        )
        levels = {}
        for number, name in LEVELS.items():
            levels[number], _ = ClassLevel.objects.get_or_create(
                curriculum=cur, level_number=number, defaults={"name": name}
            )
        made = 0
        for code, name in NEW_SUBJECTS.items():
            sd, created = SubjectDefinition.objects.get_or_create(
                curriculum=cur, code=code, defaults={"name": name}
            )
            sd.class_levels.add(levels[7], levels[8], levels[9])
            made += created
        for code, name in NEW_IGCSE_SUBJECTS.items():
            sd, created = SubjectDefinition.objects.get_or_create(
                curriculum=cur, code=code, defaults={"name": name}
            )
            sd.class_levels.add(levels[10], levels[11])
            made += created
        self.stdout.write(f"Subject definitions added: {made}.")
