from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from learning.models import LearningAuditEvent, LearningContentRole, LearningResource
from learning.test_content_api import BASE
from schools.models import School, SchoolAdminProfile, TeacherProfile

User = get_user_model()
PLATFORM = BASE.replace("studio/", "platform/")
PW = "Content!123456"


class ContentStudioStage1Tests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name="Stage1 School", code="S1S")
        self.teacher = User.objects.create_user("s1_teacher", password=PW)
        TeacherProfile.objects.create(user=self.teacher, school=self.school)
        self.school_admin = User.objects.create_user("s1_admin", password=PW)
        SchoolAdminProfile.objects.create(user=self.school_admin, school=self.school)
        self.superuser = User.objects.create_superuser("s1_super", password=PW)
        self.staff = User.objects.create_user("s1_staff", password=PW, is_staff=True)
        self.plain = User.objects.create_user("s1_plain", password=PW)
        self.author = User.objects.create_user("s1_author", password=PW)
        self.author2 = User.objects.create_user("s1_author2", password=PW)
        self.curator = User.objects.create_user("s1_curator", password=PW)
        self.both = User.objects.create_user("s1_both", password=PW)
        for u in (self.author, self.author2, self.both):
            LearningContentRole.objects.create(user=u, role="author")
        for u in (self.curator, self.both):
            LearningContentRole.objects.create(user=u, role="curator")

    def payload(self, **o):
        d = {
            "title": "Platform lesson", "summary": "A Marian lesson.",
            "body": "Original Marian text.", "language_code": "en",
            "practice_quiz": {}, "age_min": 10, "age_max": 16,
            "source_name": "Marian", "license_name": "Marian-owned",
            "attribution": "Created by Marian.",
        }
        d.update(o)
        return d

    def create(self, user, **o):
        self.client.force_authenticate(user)
        return self.client.post(PLATFORM + "resources/", self.payload(**o), format="json")

    def submit(self, user, rid):
        self.client.force_authenticate(user)
        return self.client.post(PLATFORM + f"resources/{rid}/submit/", {}, format="json")

    def review(self, user, rid, decision="approve"):
        self.client.force_authenticate(user)
        return self.client.post(PLATFORM + f"resources/{rid}/review/", {"decision": decision}, format="json")

    def test_draft_is_invisible_to_everyone_else(self):
        r = self.create(self.author)
        self.assertEqual(r.status_code, 201, r.content)
        rid = r.json()["id"]
        for u in (self.author2,):
            self.client.force_authenticate(u)
            self.assertEqual(self.client.get(PLATFORM + f"resources/{rid}/").status_code, 404)
            ids = [x["id"] for x in self.client.get(PLATFORM + "resources/").json()["results"]]
            self.assertNotIn(rid, ids)
        self.client.force_authenticate(self.curator)
        self.assertEqual(self.client.get(PLATFORM + f"resources/{rid}/").status_code, 403)
        self.assertEqual(self.client.get(PLATFORM + "review-queue/").json()["results"], [])
        for u in (self.plain, self.superuser, self.staff, self.teacher):
            self.client.force_authenticate(u)
            self.assertEqual(self.client.get(PLATFORM + f"resources/{rid}/").status_code, 403)
        for u in (self.teacher, self.school_admin):
            self.client.force_authenticate(u)
            ids = [x["id"] for x in self.client.get(BASE + "resources/").json()["results"]]
            self.assertNotIn(rid, ids)

    def test_superuser_and_staff_cannot_author(self):
        for u in (self.superuser, self.staff, self.plain):
            self.assertEqual(self.create(u).status_code, 403)

    def test_author_cannot_review_own_work(self):
        rid = self.create(self.both).json()["id"]
        self.assertEqual(self.submit(self.both, rid).status_code, 200)
        r = self.review(self.both, rid)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(LearningResource.objects.get(pk=rid).status, "in_review")

    def test_only_curators_review_platform_content(self):
        rid = self.create(self.author).json()["id"]
        self.assertEqual(self.submit(self.author, rid).status_code, 200)
        for u in (self.superuser, self.staff, self.author2, self.plain, self.school_admin):
            self.assertEqual(self.review(u, rid).status_code, 403)
        r = self.review(self.curator, rid)
        self.assertEqual(r.status_code, 200, r.content)
        obj = LearningResource.objects.get(pk=rid)
        self.assertEqual(obj.status, "approved")
        self.assertEqual(obj.reviewed_by_id, self.curator.pk)

    def test_only_superuser_grants_roles_and_it_is_audited(self):
        for u in (self.staff, self.author, self.curator, self.plain):
            self.client.force_authenticate(u)
            r = self.client.post(PLATFORM + "roles/", {"user_id": self.plain.pk, "role": "author"}, format="json")
            self.assertEqual(r.status_code, 403)
        self.assertFalse(LearningContentRole.objects.filter(user=self.plain).exists())
        self.client.force_authenticate(self.superuser)
        r = self.client.post(PLATFORM + "roles/", {"user_id": self.plain.pk, "role": "author"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        row = LearningContentRole.objects.get(user=self.plain, role="author")
        self.assertEqual(row.granted_by_id, self.superuser.pk)
        self.assertTrue(LearningAuditEvent.objects.filter(
            action="content_role_granted", actor=self.superuser, target_id=str(self.plain.pk)).exists())

    def test_disallowed_and_unpermitted_licences_rejected_at_submit(self):
        for lic in ("CC BY-NC 4.0", "CC BY-ND 4.0", "cc-by-nc-sa", "CC BY-NC-ND 4.0"):
            rid = self.create(self.author, license_name=lic).json()["id"]
            self.assertEqual(self.submit(self.author, rid).status_code, 400, lic)
        rid = self.create(self.author, license_name="Acme Commercial Licence").json()["id"]
        self.assertEqual(self.submit(self.author, rid).status_code, 400)
        rid = self.create(self.author, license_name="Acme Commercial Licence",
                          rights_notes="Written permission from Acme, 2026-11-01.").json()["id"]
        self.assertEqual(self.submit(self.author, rid).status_code, 200)
        for lic in ("CC BY 4.0", "CC BY-SA 4.0", "CC0 1.0", "Public Domain"):
            rid = self.create(self.author, license_name=lic).json()["id"]
            self.assertEqual(self.submit(self.author, rid).status_code, 200, lic)

    def test_publish_gate_still_closed(self):
        rid = self.create(self.author).json()["id"]
        self.submit(self.author, rid)
        self.review(self.curator, rid)
        self.client.force_authenticate(self.curator)
        r = self.client.post(PLATFORM + f"resources/{rid}/publish/", {}, format="json")
        self.assertEqual(r.status_code, 503)
        self.assertEqual(LearningResource.objects.get(pk=rid).status, "approved")
