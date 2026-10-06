from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from schools.models import (
    ClassLevel, Curriculum, School, SchoolAdminProfile, StaffProfile,
    Stream, Subject, TeacherAssignment, TeacherProfile)

PW = "Xk9-secure-pass"
URL = "/api/teacher-assignments/"


class StaffAssignTests(APITestCase):
    def setUp(self):
        self.a = School.objects.create(name="A", code="A1")
        self.b = School.objects.create(name="B", code="B1")
        self.boss = User.objects.create_user("boss", password=PW)
        SchoolAdminProfile.objects.create(user=self.boss, school=self.a)
        self.tu = User.objects.create_user("tu", password=PW)
        self.t = TeacherProfile.objects.create(user=self.tu, school=self.a)
        cur = Curriculum.objects.create(name="C", code="C1")
        lv = ClassLevel.objects.create(curriculum=cur, name="L1", level_number=1)
        self.st = [Stream.objects.create(school=self.a, class_level=lv, name=n)
                   for n in ("East", "West")]
        self.subj = [Subject.objects.create(school=self.a, name=f"S{i}")
                     for i in range(5)]

    def give(self, subject, stream=0, who=None):
        self.client.force_authenticate(who or self.boss)
        return self.client.post(URL, {
            "teacher": self.t.id, "subject": self.subj[subject].id,
            "stream": self.st[stream].id}, format="json")

    def test_fifth_subject_rejected(self):
        for i in range(4):
            self.assertEqual(self.give(i).status_code, 201)
        r = self.give(4)
        self.assertEqual(r.status_code, 400)
        self.assertIn("at most 4", r.json()["detail"])

    def test_more_streams_of_same_subject_allowed(self):
        for i in range(4):
            self.give(i)
        self.assertEqual(self.give(0, 1).status_code, 201)

    def test_delete_frees_a_slot(self):
        for i in range(4):
            self.give(i)
        row = TeacherAssignment.objects.filter(subject=self.subj[3]).get()
        self.client.force_authenticate(self.boss)
        self.client.delete(f"{URL}{row.id}/")
        self.assertEqual(self.give(4).status_code, 201)

    def test_teacher_and_anonymous_cannot_assign(self):
        self.assertEqual(self.give(0, who=self.tu).status_code, 403)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post(URL, {}).status_code, 401)

    def test_other_school_admin_cannot_assign(self):
        ub = User.objects.create_user("bossb", password=PW)
        SchoolAdminProfile.objects.create(user=ub, school=self.b)
        self.assertEqual(self.give(0, who=ub).status_code, 403)

    def test_bursar_me_role_and_no_data_access(self):
        u = User.objects.create_user("bur", password=PW)
        StaffProfile.objects.create(user=u, school=self.a, role="bursar")
        self.client.force_authenticate(u)
        me = self.client.get("/api/auth/me/").json()
        self.assertEqual((me["role"], me["school"]["id"]), ("bursar", self.a.id))
        self.assertEqual(self.client.get(URL).status_code, 403)
        self.assertEqual(self.give(0, who=u).status_code, 403)
