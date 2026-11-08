from rest_framework.test import APITestCase

from schools.models import (
    ClassLevel,
    Curriculum,
    School,
    SchoolAdminProfile,
    Subject,
    SubjectDefinition,
)


class SetupCatalogueTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name="Catalogue School", code="CAT1", school_type="primary")
        self.other = School.objects.create(name="Other School", code="CAT2", school_type="primary")
        self.admin = self._admin("catadmin", self.school)
        self.other_admin = self._admin("otheradmin", self.other)
        self.cbc = Curriculum.objects.create(name="Competency-Based Curriculum", code="CBC")
        self.eight_four_four = Curriculum.objects.create(name="8-4-4", code="844")
        self.cambridge = Curriculum.objects.create(name="Cambridge", code="CAMBRIDGE")
        self.g1 = self._level(self.cbc, "Grade 1", 1)
        self.g6 = self._level(self.cbc, "Grade 6", 6)
        self.g7 = self._level(self.cbc, "Grade 7", 7)
        self.g9 = self._level(self.cbc, "Grade 9", 9)
        self.g10 = self._level(self.cbc, "Grade 10", 10)
        self.g12 = self._level(self.cbc, "Grade 12", 12)
        self.form3 = self._level(self.eight_four_four, "Form 3", 3)
        self.form4 = self._level(self.eight_four_four, "Form 4", 4)
        self.cambridge7 = self._level(self.cambridge, "Lower Secondary Stage 7", 7)
        self.primary_math = self._definition("Mathematics", "MATH", [self.g1, self.g6])
        self.junior_science = self._definition("Integrated Science", "INTSCI", [self.g7, self.g9])
        self.senior_physics = self._definition("Physics", "PHY", [self.g10, self.g12])
        self.legacy_math = self._definition("Mathematics", "MATH844", [self.form3, self.form4], curriculum=self.eight_four_four)
        self.cambridge_math = self._definition("Mathematics", "CAMMATH", [self.cambridge7], curriculum=self.cambridge)

    def _admin(self, username, school):
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.create_user(username, password="pass12345")
        SchoolAdminProfile.objects.create(user=user, school=school)
        return user

    def _level(self, curriculum, name, number):
        return ClassLevel.objects.create(curriculum=curriculum, name=name, level_number=number)

    def _definition(self, name, code, levels, curriculum=None):
        definition = SubjectDefinition.objects.create(
            curriculum=curriculum or self.cbc, name=name, code=code,
        )
        definition.class_levels.add(*levels)
        return definition

    def _get(self, user=None):
        self.client.force_authenticate(user or self.admin)
        return self.client.get("/api/setup/subject-catalog/")

    def test_primary_catalog_is_grouped_and_excludes_other_levels_and_curricula(self):
        response = self._get()
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual([row["level_number"] for row in response.data["groups"]], [1, 6])
        self.assertTrue(all(row["curriculum_code"] == "CBC" for row in response.data["groups"]))
        self.assertEqual(response.data["groups"][0]["subjects"][0]["code"], "MATH")
        self.assertIn("internal catalogue codes", response.data["notice"])
        self.assertNotIn(self.cambridge_math.id, {
            item["definition_id"]
            for group in response.data["groups"]
            for item in group["subjects"]
        })

    def test_combined_is_primary_plus_junior_and_senior_includes_fixture_844(self):
        self.school.school_type = "combined"
        self.school.save(update_fields=["school_type"])
        response = self._get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {row["level_number"] for row in response.data["groups"]},
            {1, 6, 7, 9},
        )

        self.school.school_type = "senior"
        self.school.save(update_fields=["school_type"])
        response = self._get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {(row["curriculum_code"], row["level_number"]) for row in response.data["groups"]},
            {("CBC", 10), ("CBC", 12), ("844", 3), ("844", 4)},
        )

    def test_bulk_create_validates_levels_and_is_idempotent(self):
        self.client.force_authenticate(self.admin)
        invalid = self.client.post(
            "/api/setup/subjects/bulk/",
            {"selections": [{"definition_id": self.junior_science.id, "class_level_id": self.g10.id}]},
            format="json",
        )
        self.assertEqual(invalid.status_code, 400, invalid.data)

        first = self.client.post(
            "/api/setup/subjects/bulk/",
            {"selections": [
                {"definition_id": self.primary_math.id, "class_level_id": self.g1.id},
                {"definition_id": self.primary_math.id, "class_level_id": self.g1.id},
            ]},
            format="json",
        )
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual((first.data["created_count"], first.data["skipped_count"]), (1, 1))
        second = self.client.post(
            "/api/setup/subjects/bulk/",
            {"selections": [{"definition_id": self.primary_math.id, "class_level_id": self.g1.id}]},
            format="json",
        )
        self.assertEqual(second.status_code, 200, second.data)
        self.assertEqual(second.data["created_count"], 0)
        self.assertEqual(Subject.objects.filter(school=self.school).count(), 1)

    def test_catalogue_is_scoped_to_the_callers_school(self):
        Subject.objects.create(school=self.other, name="Mathematics — Grade 1", code="MATH")
        response = self._get(self.other_admin)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["school_type"], "primary")
        self.assertEqual(Subject.objects.filter(school=self.school).count(), 0)
        self.assertEqual(Subject.objects.filter(school=self.other).count(), 1)
