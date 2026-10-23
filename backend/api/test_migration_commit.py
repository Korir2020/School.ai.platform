import itertools
from datetime import date
from unittest import mock

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import models
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from api import migration_commit as mcm
from schools.models import (AcademicYear, ClassLevel, Curriculum, Enrollment,
                            MarkAuditLog, School, Stream, Student)

_n = itertools.count(1)
HEAD = "Admission No,First name,Surname,Class\n"


def make(model, **kw):
    """Create a row, filling any other required plain fields with throwaway values."""
    for f in model._meta.concrete_fields:
        if f.primary_key or f.name in kw or f.has_default() or f.null or f.blank:
            continue
        if isinstance(f, (models.CharField, models.TextField)):
            kw[f.name] = "t%d" % next(_n)
        elif isinstance(f, models.BooleanField):
            kw[f.name] = False
        elif isinstance(f, models.IntegerField):
            kw[f.name] = 1
        elif isinstance(f, models.DateTimeField):
            kw[f.name] = timezone.now()
        elif isinstance(f, models.DateField):
            kw[f.name] = date.today()
        else:
            raise AssertionError("cannot fill %s.%s" % (model.__name__, f.name))
    return model.objects.create(**kw)


class CommitTests(TestCase):
    def setUp(self):
        self.school = make(School, name="Test School")
        self.user = User.objects.create(username="admin")
        cur = make(Curriculum, name="Test")
        self.g7 = make(ClassLevel, curriculum=cur, name="Grade 7", level_number=7)
        self.g10 = make(ClassLevel, curriculum=cur, name="Grade 10", level_number=10)
        make(Stream, school=self.school, class_level=self.g7, name="East")
        make(Stream, school=self.school, class_level=self.g10, name="East")
        self.year = make(AcademicYear, school=self.school, name="2026",
                         start_date=date(2026, 1, 1), end_date=date(2026, 12, 1), is_active=True)

    def post(self, csv, admin=True):
        req = APIRequestFactory().post("/x/", {"file": SimpleUploadedFile("a.csv", csv.encode())}, format="multipart")
        force_authenticate(req, user=self.user)
        with mock.patch.object(mcm, "_scope", return_value=(self.school.id, None)), \
             mock.patch.object(mcm, "_admin", return_value=admin):
            return mcm.migration_commit(req)

    def test_adds_only_ready_rows(self):
        resp = self.post(HEAD + "1001,Amina,Otieno,Grade 7 East\n1002,Brian,Kamau,Grade 99\n")
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual((resp.data["created"], resp.data["skipped"]), (1, 1))
        self.assertEqual(list(Student.objects.values_list("admission_number", flat=True)), ["1001"])
        enr = Enrollment.objects.get()
        self.assertEqual((enr.class_level_id, enr.academic_year_id), (self.g7.id, self.year.id))
        self.assertEqual(enr.stream.name, "East")
        self.assertEqual(MarkAuditLog.objects.filter(action="student_migration_import").count(), 1)

    def test_same_file_twice_adds_nothing_more(self):
        csv = HEAD + "1001,Amina,Otieno,Grade 7 East\n"
        self.assertEqual(self.post(csv).status_code, 201)
        self.assertEqual(self.post(csv).status_code, 400)
        self.assertEqual(Student.objects.count(), 1)
        self.assertEqual(Enrollment.objects.count(), 1)

    def test_nothing_ready_adds_nothing(self):
        resp = self.post(HEAD + "1002,Brian,Kamau,Grade 99\n")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Student.objects.count(), 0)

    def test_no_active_year_adds_nothing(self):
        AcademicYear.objects.update(is_active=False)
        resp = self.post(HEAD + "1001,Amina,Otieno,Grade 7 East\n")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Student.objects.count(), 0)

    def test_non_admin_blocked(self):
        resp = self.post(HEAD + "1001,Amina,Otieno,Grade 7 East\n", admin=False)
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(Student.objects.count(), 0)

    def test_senior_learner_keeps_assessment_number(self):
        resp = self.post("Admission No,First name,Surname,Class,Assessment Number\n2001,Zawadi,Mwangi,Grade 10 East,A123\n")
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual(Student.objects.get().assessment_number, "A123")
