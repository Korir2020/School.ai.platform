from io import StringIO

from django.core.management import call_command
from rest_framework.test import APITestCase

from schools.models import (
    ClassLevel, Curriculum, School, Subject, SubjectDefinition,
)


def run():
    call_command("extend_cambridge_catalogue", stdout=StringIO())


class CambridgeCatalogueTests(APITestCase):
    def setUp(self):
        self.cur = Curriculum.objects.create(name="Cambridge International", code="CAMBRIDGE")
        lvl = ClassLevel.objects.create(
            curriculum=self.cur, name="Lower Secondary Stage 7", level_number=7)
        self.math = SubjectDefinition.objects.create(
            curriculum=self.cur, name="Mathematics", code="MATH")
        self.math.class_levels.add(lvl)
        school = School.objects.create(name="S", code="S1")
        self.subject = Subject.objects.create(school=school, name="Maths", definition=self.math)

    def test_scope_is_lower_secondary_and_igcse_only(self):
        run()
        numbers = set(ClassLevel.objects.filter(curriculum=self.cur).values_list("level_number", flat=True))
        self.assertEqual(numbers, {7, 8, 9, 10, 11})

    def test_adds_computing_and_ict_starters_for_stages_7_to_9(self):
        run()
        for code in ("COMPUTING", "ICTSTART"):
            sd = SubjectDefinition.objects.get(curriculum=self.cur, code=code)
            self.assertEqual(set(sd.class_levels.values_list("level_number", flat=True)), {7, 8, 9})

    def test_existing_records_preserved(self):
        run()
        self.subject.refresh_from_db()
        self.assertEqual(self.subject.definition_id, self.math.id)
        self.assertEqual(set(self.math.class_levels.values_list("level_number", flat=True)), {7})

    def test_running_twice_creates_no_duplicates(self):
        run()
        counts = (ClassLevel.objects.count(), SubjectDefinition.objects.count())
        run()
        self.assertEqual((ClassLevel.objects.count(), SubjectDefinition.objects.count()), counts)
