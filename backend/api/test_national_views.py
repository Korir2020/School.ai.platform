from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from schools.models import (
    AcademicYear, ClassLevel, Curriculum, School, SchoolAdminProfile, Stream,
    Student, TeacherProfile,
)

CT = "/api/records/class-teachers/"
NR = "/api/records/national/"


class NationalViewsTests(TestCase):
    def setUp(self):
        U = get_user_model()
        self.school = School.objects.create(name="Nv School", code="nv-test")
        self.other = School.objects.create(name="Nv Other", code="nv-other")
        self.admin = U.objects.create_user("nv_admin", "a@example.com", "pw12345!")
        SchoolAdminProfile.objects.create(user=self.admin, school=self.school)
        self.outsider = U.objects.create_user("nv_out", "o@example.com", "pw12345!")
        SchoolAdminProfile.objects.create(user=self.outsider, school=self.other)
        self.tuser = U.objects.create_user("nv_teacher", "t@example.com", "pw12345!")
        self.tp = TeacherProfile.objects.create(user=self.tuser, school=self.school)
        cur = Curriculum.objects.create(name="Nv CBC", code="NVCBC")
        g3 = ClassLevel.objects.create(curriculum=cur, name="Grade 3", level_number=3)
        self.east = Stream.objects.create(school=self.school, class_level=g3, name="East")
        self.year = AcademicYear.objects.create(
            school=self.school, name="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        self.kid = Student.objects.create(
            school=self.school, first_name="Amani", last_name="Test", admission_number="A1")

    def _c(self, user=None):
        c = APIClient()
        if user:
            c.force_authenticate(user)
        return c

    def _assign(self, user=None):
        return self._c(user or self.admin).post(CT, {
            "stream_id": self.east.id, "year_id": self.year.id, "teacher_id": self.tp.id}, format="json")

    def _save(self, **kw):
        body = {"student_id": self.kid.id, "exam_type": "kjsea", "year": 2026,
                "subject_name": "", "result": "TEST-RESULT"}
        body.update(kw)
        return self._c(self.admin).post(NR, body, format="json")

    def test_teacher_cannot_manage_class_teachers(self):
        self.assertEqual(self._c(self.tuser).get(CT).status_code, 403)
        self.assertEqual(self._assign(self.tuser).status_code, 403)

    def test_assign_and_list_class_teacher(self):
        r = self._assign()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["teacher_id"], self.tp.id)
        rows = self._c(self.admin).get(CT).data["class_teachers"]
        self.assertEqual(len(rows), 1)

    def test_reassigning_replaces_not_duplicates(self):
        self._assign()
        self._assign()
        self.assertEqual(len(self._c(self.admin).get(CT).data["class_teachers"]), 1)

    def test_other_school_cannot_assign_this_teacher(self):
        self.assertEqual(self._assign(self.outsider).status_code, 404)

    def test_save_and_list_national_record(self):
        self.assertEqual(self._save().status_code, 200)
        rows = self._c(self.admin).get(NR + "?student_id=%d" % self.kid.id).data["records"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["result"], "TEST-RESULT")

    def test_saving_again_updates_the_same_row(self):
        self._save()
        self._save(result="CHANGED")
        rows = self._c(self.admin).get(NR).data["records"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["result"], "CHANGED")

    def test_unknown_exam_type_and_empty_result_are_refused(self):
        self.assertEqual(self._save(exam_type="kcpe").status_code, 400)
        self.assertEqual(self._save(result="  ").status_code, 400)
        self.assertEqual(self._save(year="abc").status_code, 400)

    def test_other_school_cannot_record_for_this_student(self):
        r = self._c(self.outsider).post(NR, {
            "student_id": self.kid.id, "exam_type": "kjsea", "year": 2026, "result": "X"}, format="json")
        self.assertEqual(r.status_code, 404)

    def test_options_list_streams_teachers_and_years(self):
        r = self._c(self.admin).get(CT)
        self.assertEqual(r.status_code, 200)
        opt = r.data["options"]
        self.assertEqual([s["id"] for s in opt["streams"]], [self.east.id])
        self.assertEqual([t["id"] for t in opt["teachers"]], [self.tp.id])
        self.assertEqual([y["id"] for y in opt["years"]], [self.year.id])
        self.assertEqual(opt["streams"][0]["name"], "Grade 3 East")
