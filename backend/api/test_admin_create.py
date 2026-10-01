from datetime import date

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from schools.models import (
    AcademicYear, ClassLevel, Curriculum, Enrollment, School,
    SchoolAdminProfile, Stream, Student, Subject, TeacherAssignment,
    TeacherProfile,
)

YEAR = {"name": "2027", "start_date": "2027-01-01", "end_date": "2027-12-31"}


class AdminCreateTests(APITestCase):
    def setUp(self):
        self.a = School.objects.create(name="A", code="A1")
        self.b = School.objects.create(name="B", code="B1")
        self.admin = User.objects.create_user("admin_a", password="pass12345")
        SchoolAdminProfile.objects.create(user=self.admin, school=self.a)
        self.t_user = User.objects.create_user("t_a", password="pass12345")
        self.teacher = TeacherProfile.objects.create(user=self.t_user, school=self.a)
        tb = User.objects.create_user("t_b", password="pass12345")
        self.teacher_b = TeacherProfile.objects.create(user=tb, school=self.b)
        self.root = User.objects.create_superuser("root", "r@x.com", "pass12345")

        self.year_a = AcademicYear.objects.create(
            school=self.a, name="2026",
            start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        self.year_b = AcademicYear.objects.create(
            school=self.b, name="2026",
            start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        cur = Curriculum.objects.create(name="C", code="C1")
        self.l1 = ClassLevel.objects.create(curriculum=cur, name="L1", level_number=1)
        self.l2 = ClassLevel.objects.create(curriculum=cur, name="L2", level_number=2)
        self.stream_a = Stream.objects.create(school=self.a, class_level=self.l1, name="East")
        self.stream_b = Stream.objects.create(school=self.b, class_level=self.l1, name="West")
        self.stu_a = Student.objects.create(
            school=self.a, first_name="A", last_name="A", admission_number="A-1")
        self.stu_b = Student.objects.create(
            school=self.b, first_name="B", last_name="B", admission_number="B-1")
        self.subj_a = Subject.objects.create(school=self.a, name="Math")
        self.subj_b = Subject.objects.create(school=self.b, name="Math")

    def post(self, user, url, body):
        self.client.force_authenticate(user)
        return self.client.post(url, body, format="json")

    def test_anonymous_gets_401_everywhere(self):
        for url in ["academic-years", "terms", "streams", "subjects",
                    "enrollments", "teacher-assignments"]:
            self.assertEqual(self.client.post(f"/api/{url}/", {}).status_code, 401, url)

    def test_teacher_gets_403_everywhere(self):
        for url in ["academic-years", "terms", "streams", "subjects",
                    "enrollments", "teacher-assignments"]:
            self.assertEqual(self.post(self.t_user, f"/api/{url}/", {}).status_code, 403, url)

    def test_year_forced_into_own_school(self):
        r = self.post(self.admin, "/api/academic-years/", {**YEAR, "school": self.b.id})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(AcademicYear.objects.get(name="2027").school_id, self.a.id)

    def test_year_bad_dates_400(self):
        body = {**YEAR, "start_date": "2027-12-31", "end_date": "2027-01-01"}
        self.assertEqual(self.post(self.admin, "/api/academic-years/", body).status_code, 400)

    def test_term_rules(self):
        ok = {"academic_year": self.year_a.id, "name": "T1",
              "start_date": "2026-01-05", "end_date": "2026-04-05"}
        self.assertEqual(self.post(self.admin, "/api/terms/", ok).status_code, 201)
        outside = {**ok, "name": "T2", "end_date": "2027-04-05"}
        self.assertEqual(self.post(self.admin, "/api/terms/", outside).status_code, 400)
        other = {**ok, "academic_year": self.year_b.id}
        self.assertEqual(self.post(self.admin, "/api/terms/", other).status_code, 403)

    def test_stream_and_subject_forced_into_own_school(self):
        r = self.post(self.admin, "/api/streams/",
                      {"school": self.b.id, "class_level": self.l1.id, "name": "North"})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(Stream.objects.get(name="North").school_id, self.a.id)
        r = self.post(self.admin, "/api/subjects/", {"school": self.b.id, "name": "Art"})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(Subject.objects.get(name="Art").school_id, self.a.id)

    def test_enrollment_rules(self):
        body = {"student": self.stu_a.id, "academic_year": self.year_a.id,
                "class_level": self.l1.id, "stream": self.stream_a.id}
        self.assertEqual(self.post(self.admin, "/api/enrollments/", {**body, "student": self.stu_b.id}).status_code, 403)
        self.assertEqual(self.post(self.admin, "/api/enrollments/", {**body, "class_level": self.l2.id}).status_code, 400)
        self.assertEqual(self.post(self.admin, "/api/enrollments/", body).status_code, 201)
        self.assertEqual(self.post(self.admin, "/api/enrollments/", body).status_code, 400)

    def test_teacher_assignment_rules(self):
        body = {"teacher": self.teacher.id, "subject": self.subj_a.id,
                "stream": self.stream_a.id}
        r = self.post(self.admin, "/api/teacher-assignments/", {**body, "teacher": self.teacher_b.id})
        self.assertEqual(r.status_code, 403)
        r = self.post(self.admin, "/api/teacher-assignments/", {**body, "school": self.b.id})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(TeacherAssignment.objects.get().school_id, self.a.id)
        self.assertEqual(self.post(self.admin, "/api/teacher-assignments/", body).status_code, 400)

    def test_superuser_mixed_schools_400(self):
        body = {"teacher": self.teacher.id, "subject": self.subj_b.id,
                "stream": self.stream_a.id, "school": self.a.id}
        self.assertEqual(self.post(self.root, "/api/teacher-assignments/", body).status_code, 400)
