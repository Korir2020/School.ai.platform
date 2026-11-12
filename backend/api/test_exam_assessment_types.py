from datetime import date

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from schools.models import AcademicYear, ClassLevel, Curriculum, School, SchoolAdminProfile, Term


class ExaminationAssessmentTypeTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name="Assessment School", code="ATS")
        year = AcademicYear.objects.create(school=self.school, name="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        self.term = Term.objects.create(academic_year=year, name="T1", start_date=date(2026, 1, 1), end_date=date(2026, 4, 1))
        curriculum = Curriculum.objects.create(name="Assessment Curriculum", code="ATC")
        self.level = ClassLevel.objects.create(curriculum=curriculum, name="G7", level_number=7)
        self.admin = User.objects.create_user("assessment_admin", password="pass12345")
        SchoolAdminProfile.objects.create(user=self.admin, school=self.school)

    def create(self, name, kind):
        self.client.force_authenticate(self.admin)
        return self.client.post("/api/exams/", {
            "name": name, "term": self.term.id, "assessment_type": kind, "class_level": self.level.id,
        }, format="json")

    def test_each_assessment_type_is_available_once_per_class_and_term(self):
        for kind in ("opener", "mid", "end"):
            response = self.create(kind.title(), kind)
            self.assertEqual(response.status_code, 201, response.data)
            self.assertEqual(response.data["assessment_type"], kind)
        duplicate = self.create("Second end-term", "end")
        self.assertEqual(duplicate.status_code, 400)
