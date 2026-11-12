"""API tests for api/report_views.py (needs marian_reports)."""
import hashlib
import shutil
import subprocess
import unittest
from datetime import date
try:
    import marian_reports  # noqa: F401
except ImportError:
    raise unittest.SkipTest("marian_reports is not installed")

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient
from marian_reports.grading import make_scheme
from schools.models import (
    AcademicYear, ClassLevel, Curriculum, Enrollment, Exam, GuardianProfile,
    Performance, School, SchoolAdminProfile, Stream, Student, StudentGuardian,
    Subject, SubjectRegistration, TeacherAssignment, TeacherProfile, Term,
    PublishedReportArtifact, ReportSettings,
)
from api.report_access import build_report_user
from api.report_source import DjangoConfigStore
from api.report_views import service

B = "/api/report-module/"
BANDS = [("E", 0, 50, 1), ("C", 50, 70, 2), ("A", 70, 100, 3)]


def mkuser(name):
    return get_user_model().objects.create_user(
        username=name, email=f"{name}@x.test", password="pw-12345!")


class ApiCase(TestCase):
    def setUp(self):
        cur = Curriculum.objects.create(name="CBC", code="CBC")
        mk = lambda n, k: ClassLevel.objects.create(curriculum=cur, name=n, level_number=k)
        self.level, l4 = mk("Form 3", 3), mk("Form 4", 4)
        self.school = School.objects.create(name="Alpha", code="ALPHA", location="Nairobi", phone="0700")
        self.other = School.objects.create(name="Beta", code="BETA")
        self.third = School.objects.create(name="Gamma", code="GAMMA")
        year = AcademicYear.objects.create(school=self.school, name="2026", start_date=date(2026, 1, 5), end_date=date(2026, 11, 27))
        term = Term.objects.create(academic_year=year, name="Term 3", start_date=date(2026, 8, 31), end_date=date(2026, 10, 23))
        east = Stream.objects.create(school=self.school, class_level=self.level, name="East")
        west4 = Stream.objects.create(school=self.school, class_level=l4, name="West")
        maths = Subject.objects.create(school=self.school, name="Mathematics", code="MAT")
        sci = Subject.objects.create(school=self.school, name="Science", code="SCI")

        def stu(adm, first):
            s = Student.objects.create(school=self.school, first_name=first, last_name="Test", admission_number=adm)
            Enrollment.objects.create(student=s, academic_year=year, class_level=self.level, stream=east)
            for sub, m in ((maths, 70), (sci, 55)):
                SubjectRegistration.objects.create(
                    student=s, academic_year=year, subject=sub, category="compulsory")
                Performance.objects.create(student=s, subject=sub, academic_year=year, term=term,
                                           assessment_type="end", paper_number=1, marks=m, status="approved")
            return s
        self.s1, self.s2 = stu("A-1", "Amina"), stu("A-2", "Brian")
        self.exam = Exam.objects.create(school=self.school, name="End Term 3", term=term, assessment_type="end",
                                        class_level=self.level, status="published")
        scheme = make_scheme(BANDS, pass_pct=50)
        for sc in (self.school, self.other):
            DjangoConfigStore(str(sc.id)).save_scheme(scheme)
        self.admin = mkuser("adm"); SchoolAdminProfile.objects.create(user=self.admin, school=self.school)
        self.admin2 = mkuser("adm2"); SchoolAdminProfile.objects.create(user=self.admin2, school=self.other)
        self.admin3 = mkuser("adm3"); SchoolAdminProfile.objects.create(user=self.admin3, school=self.third)
        self.gua = mkuser("gua"); g = GuardianProfile.objects.create(user=self.gua, school=self.school)
        StudentGuardian.objects.create(student=self.s1, guardian=g)
        self.t3, self.t4 = mkuser("t3"), mkuser("t4")
        for u, st in ((self.t3, east), (self.t4, west4)):
            tp = TeacherProfile.objects.create(user=u, school=self.school, staff_id=u.username)
            TeacherAssignment.objects.create(teacher=tp, school=self.school, subject=maths, stream=st)
        self.q = {"exam_id": str(self.exam.pk), "class_name": "Form 3"}

    def get(self, path, user=None, params=None):
        c = APIClient()
        if user:
            c.force_authenticate(user)
        return c.get(B + path, self.q if params is None else params)

    def test_requires_login(self):
        self.assertIn(self.get("meta/").status_code, (401, 403))

    def test_no_grading_scale_gives_422(self):
        r = self.get("meta/", self.admin3)
        self.assertEqual((r.status_code, r.data["error"]), (422, "no_grading_scale"))

    def test_admin_meta_lists_only_own_school(self):
        r = self.get("meta/", self.admin)
        self.assertEqual((r.status_code, r.data["role"]), (200, "admin"))
        self.assertEqual(sorted(s["adm_no"] for s in r.data["students"]), ["A-1", "A-2"])

    def test_selection_counts(self):
        d = self.get("selection/", self.admin).data
        self.assertEqual((d["selected"], d["eligible"], d["complete"], d["excluded"]), (2, 2, 2, []))

    def test_guardian_pdf_own_child(self):
        r = self.get(f"student/{self.s1.pk}/pdf/", self.gua)
        self.assertEqual((r.status_code, r["Content-Type"]), (200, "application/pdf"))
        self.assertTrue(r.content.startswith(b"%PDF"))
        self.assertIn("inline", r["Content-Disposition"])

    def test_guardian_cannot_open_other_child(self):
        self.assertEqual(self.get(f"student/{self.s2.pk}/pdf/", self.gua).status_code, 403)

    def test_guardian_blocked_from_class_endpoints(self):
        for p in ("selection/", "analytics/", "rankings/", "support-list/", "export/csv/"):
            self.assertEqual(self.get(p, self.gua).status_code, 403, p)

    def test_other_school_gets_404(self):
        for p in ("selection/", "analytics/", f"student/{self.s1.pk}/pdf/"):
            self.assertEqual(self.get(p, self.admin2).status_code, 404, p)

    def test_teachers_cannot_open_reports(self):
        for t in (self.t3, self.t4):
            for p in ("selection/", "export/csv/", "analytics/", f"student/{self.s1.pk}/pdf/"):
                self.assertEqual(self.get(p, t).status_code, 403, p)

    def test_rankings_analytics_support(self):
        r = self.get("rankings/", self.admin)
        self.assertEqual((r.status_code, r.data["included"]), (200, 2))
        r = self.get("analytics/", self.admin)
        self.assertEqual(r.status_code, 200); self.assertIn("population", r.data)
        self.assertEqual(self.get("support-list/", self.admin).status_code, 200)
        self.assertEqual(self.get("rankings/", self.admin, {**self.q, "scope": "bad"}).status_code, 422)

    def test_export_csv_and_bad_format(self):
        r = self.get("export/csv/", self.admin)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r["Content-Type"].startswith("text/csv"))
        self.assertIn("A-1", r.content.decode("utf-8-sig"))
        self.assertEqual(self.get("export/exe/", self.admin).status_code, 404)

    def test_verify_with_exam_id(self):
        user, svc = build_report_user(self.admin), service(self.school.id)
        snap = svc.snapshot(user, str(self.exam.pk), "Form 3")
        rd = svc.build_report(user, snap, str(self.s1.pk))
        url = f"{B}verify/{rd.report_no}/"
        q = {"s": str(self.school.id), "t": rd.token}
        self.assertEqual(APIClient().get(url, {**q, "e": str(self.exam.pk)}).status_code, 200)
        self.assertEqual(APIClient().get(url, {**q, "e": "999999"}).status_code, 404)

    def test_verify_valid_and_tampered(self):
        user, svc = build_report_user(self.admin), service(self.school.id)
        snap = svc.snapshot(user, str(self.exam.pk), "Form 3")
        rd = svc.build_report(user, snap, str(self.s1.pk))
        url = f"{B}verify/{rd.report_no}/"
        ok = APIClient().get(url, {"s": str(self.school.id), "t": rd.token})
        self.assertEqual((ok.status_code, ok.data["valid"]), (200, True))
        self.assertNotIn("Amina", str(ok.data))
        bad = APIClient().get(url, {"s": str(self.school.id), "t": "000000000000"})
        self.assertEqual(bad.status_code, 404)

    def test_published_pdf_is_archived_immutable_and_exam_qualified(self):
        client = APIClient()
        client.force_authenticate(self.admin)
        path = f"{B}student/{self.s1.pk}/pdf/"
        first = client.get(path, {"exam_id": str(self.exam.pk)})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first["X-Report-Archived"], "true")
        self.assertEqual(self.get(f"student/{self.s1.pk}/pdf/", self.gua,
                                  {"exam_id": str(self.exam.pk)}).status_code, 200)
        self.assertEqual(self.get(f"student/{self.s2.pk}/pdf/", self.gua,
                                  {"exam_id": str(self.exam.pk)}).status_code, 403)
        self.assertEqual(self.get(f"student/{self.s1.pk}/pdf/", self.admin2,
                                  {"exam_id": str(self.exam.pk)}).status_code, 404)
        self.assertEqual(self.get(f"student/{self.s1.pk}/pdf/", self.t3,
                                  {"exam_id": str(self.exam.pk)}).status_code, 403)
        artifact = PublishedReportArtifact.objects.get(exam=self.exam, student=self.s1)
        self.assertEqual(artifact.report_no, f"RPT-E{self.exam.pk}-A-1")
        self.assertEqual(artifact.sha256, hashlib.sha256(first.content).hexdigest())
        text = self._pdf_text_if_available(first.content)
        if text is not None:
            self.assertIn(artifact.report_no, text)

        # Even if a privileged data repair changes the live source later, the
        # issued bytes and their public verification remain tied to the archive.
        Performance.objects.filter(
            student=self.s1, term=self.exam.term, assessment_type="end",
            subject__name="Mathematics").update(marks=1)
        ReportSettings.objects.filter(school=self.school).delete()
        second = client.get(path, {"exam_id": str(self.exam.pk)})
        self.assertEqual(second.content, first.content)
        verify = APIClient().get(
            f"{B}verify/{artifact.report_no}/",
            {"s": str(self.school.pk), "t": artifact.verification_token,
             "e": str(self.exam.pk)},
        )
        self.assertEqual((verify.status_code, verify.data["valid"]), (200, True))
        DjangoConfigStore(str(self.school.pk)).save_scheme(make_scheme(BANDS, pass_pct=50))
        altered = PublishedReportArtifact.objects.get(pk=artifact.pk)
        altered.report_no = "changed"
        with self.assertRaises(ValidationError):
            altered.save()

        # A second published exam in the same term must have a different ID.
        mid_exam = Exam.objects.create(
            school=self.school, name="Mid Term 3", term=self.exam.term,
            assessment_type="mid", class_level=self.level, status="published")
        for row in Performance.objects.filter(
                student=self.s1, term=self.exam.term, assessment_type="end"):
            Performance.objects.create(
                student=self.s1, subject=row.subject, academic_year=row.academic_year,
                term=row.term, assessment_type="mid", paper_number=row.paper_number,
                marks=row.marks, status="approved")
        another = client.get(path, {"exam_id": str(mid_exam.pk)})
        self.assertEqual(another.status_code, 200)
        second_artifact = PublishedReportArtifact.objects.get(exam=mid_exam, student=self.s1)
        self.assertEqual(second_artifact.report_no, f"RPT-E{mid_exam.pk}-A-1")
        self.assertNotEqual(artifact.report_no, second_artifact.report_no)
        self.assertEqual(PublishedReportArtifact.objects.filter(student=self.s1).count(), 2)
        text = self._pdf_text_if_available(another.content)
        if text is not None:
            self.assertIn(second_artifact.report_no, text)

    def _pdf_text_if_available(self, content):
        if not shutil.which("pdftotext"):
            return None
        result = subprocess.run(
            ["pdftotext", "-", "-"], input=content, capture_output=True, check=True)
        return result.stdout.decode("utf-8", "replace")
