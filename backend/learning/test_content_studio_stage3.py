from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from learning.models import LearningResource
from learning.test_content_api import BASE
from schools.models import School, SchoolAdminProfile, TeacherProfile

User = get_user_model()
PW = "Content!123456"


class ContentStudioStage3Tests(APITestCase):
    def mk(self, name, school):
        u = User.objects.create_user(name, password=PW)
        TeacherProfile.objects.create(user=u, school=school)
        return u

    def setUp(self):
        self.school = School.objects.create(name="S3 School", code="S3A")
        self.other = School.objects.create(name="S3 Other", code="S3B")
        self.teacher = self.mk("s3_teacher", self.school)
        self.teacher2 = self.mk("s3_teacher2", self.school)
        self.outsider = self.mk("s3_outsider", self.other)
        self.admin = User.objects.create_user("s3_admin", password=PW)
        SchoolAdminProfile.objects.create(user=self.admin, school=self.school)
        self.src = LearningResource.objects.create(
            scope="school", school=self.school, author=self.teacher,
            status="draft", version=1, title="Fractions", summary="S",
            body="Body", language_code="en", resource_type="lesson",
            source_name="Acme", license_name="CC BY 4.0",
            license_url="https://creativecommons.org/licenses/by/4.0/",
            attribution="By Acme", rights_notes="note",
            source_type="open_licensed",
            license_verified_by=self.admin,
            license_verified_at=timezone.now(),
        )

    def dup(self, user):
        self.client.force_authenticate(user)
        url = BASE + f"resources/{self.src.pk}/duplicate/"
        return self.client.post(url, {}, format="json")

    def test_stage3_owner_copy_is_draft_with_parent(self):
        r = self.dup(self.teacher)
        self.assertEqual(r.status_code, 201, r.content)
        c = LearningResource.objects.get(pk=r.json()["id"])
        self.assertEqual(c.parent_id, self.src.pk)
        self.assertEqual((c.status, c.version), ("draft", 1))
        self.assertEqual(c.author_id, self.teacher.pk)
        self.assertEqual(c.school_id, self.school.pk)

    def test_stage3_copy_keeps_licence_and_attribution(self):
        c = LearningResource.objects.get(pk=self.dup(self.teacher).json()["id"])
        for f in ("source_name", "license_name", "license_url",
                  "attribution", "rights_notes", "source_type"):
            self.assertEqual(getattr(c, f), getattr(self.src, f), f)

    def test_stage3_copy_needs_reverification(self):
        c = LearningResource.objects.get(pk=self.dup(self.teacher).json()["id"])
        self.assertIsNone(c.license_verified_by_id)
        self.assertIsNone(c.license_verified_at)

    def test_stage3_other_teacher_and_other_school_get_404(self):
        self.assertEqual(self.dup(self.teacher2).status_code, 404)
        self.assertEqual(self.dup(self.outsider).status_code, 404)

    def test_stage3_school_admin_can_copy(self):
        r = self.dup(self.admin)
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["author_id"], self.admin.pk)

    def test_stage3_original_unchanged(self):
        self.dup(self.teacher)
        self.src.refresh_from_db()
        self.assertEqual((self.src.status, self.src.version), ("draft", 1))
        self.assertIsNone(self.src.parent_id)
