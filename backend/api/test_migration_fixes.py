import json
from datetime import date
from unittest import mock

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from api import migration_commit as mcm
from api.migration_check import UploadError, _fixes
from api.migration_rules import analyse_upload
from api.test_migration_commit import make
from schools.models import (AcademicYear, ClassLevel, Curriculum, School, Stream, Student)

STRUCT = [{"id": 1, "name": "Grade 7", "level_number": 7, "streams": [{"id": 11, "name": "East"}]}]
HEAD = ["Admission No", "First name", "Surname", "Class"]


def by(res):
    return {r["row"]: r for r in res["rows"]}


class FixRuleTests(SimpleTestCase):
    def test_fix_missing_surname(self):
        m = [HEAD, ["1004", "David", "", "Grade 7 East"]]
        self.assertEqual(by(analyse_upload(m, STRUCT))[2]["status"], "blocked")
        after = by(analyse_upload(m, STRUCT, fixes={2: {"last_name": "Mwangi"}}))[2]
        self.assertEqual((after["status"], after["last_name"]), ("ready", "Mwangi"))

    def test_fix_duplicate_admission(self):
        m = [HEAD, ["1001", "Amina", "Otieno", "Grade 7 East"], ["1001", "Brian", "Kamau", "Grade 7 East"]]
        self.assertTrue(any(r["status"] == "blocked" for r in analyse_upload(m, STRUCT)["rows"]))
        after = by(analyse_upload(m, STRUCT, fixes={3: {"admission_number": "1002"}}))
        self.assertEqual((after[2]["status"], after[3]["status"]), ("ready", "ready"))

    def test_fix_class(self):
        m = [HEAD, ["1005", "Cate", "Wanjiru", "Grade 99"]]
        self.assertEqual(by(analyse_upload(m, STRUCT))[2]["status"], "blocked")
        after = by(analyse_upload(m, STRUCT, fixes={2: {"class_level": "Grade 7 East"}}))[2]
        self.assertEqual((after["status"], after["class_label"]), ("ready", "Grade 7 East"))

    def test_fix_does_not_touch_other_rows(self):
        m = [HEAD, ["1001", "Amina", "Otieno", "Grade 7 East"], ["1002", "Brian", "Kamau", "Grade 7 East"]]
        after = by(analyse_upload(m, STRUCT, fixes={3: {"last_name": "Zed"}}))
        self.assertEqual((after[2]["last_name"], after[3]["last_name"]), ("Otieno", "Zed"))

    def test_fixes_parse_ok(self):
        self.assertEqual(_fixes('{"2": {"last_name": " X "}}'), {2: {"last_name": "X"}})
        self.assertIsNone(_fixes(""))

    def test_fixes_bad_json(self):
        with self.assertRaises(UploadError):
            _fixes("not json")

    def test_fixes_unknown_field(self):
        with self.assertRaises(UploadError):
            _fixes('{"2": {"is_staff": "x"}}')

    def test_fixes_not_string(self):
        with self.assertRaises(UploadError):
            _fixes('{"2": {"last_name": 5}}')


class FixCommitTests(TestCase):
    def setUp(self):
        self.school = make(School, name="Test School")
        self.user = User.objects.create(username="admin")
        cur = make(Curriculum, name="Test")
        g7 = make(ClassLevel, curriculum=cur, name="Grade 7", level_number=7)
        make(Stream, school=self.school, class_level=g7, name="East")
        make(AcademicYear, school=self.school, name="2026", start_date=date(2026, 1, 1),
             end_date=date(2026, 12, 1), is_active=True)

    def post(self, csv, fixes=None):
        data = {"file": SimpleUploadedFile("a.csv", csv.encode())}
        if fixes is not None:
            data["fixes"] = json.dumps(fixes)
        req = APIRequestFactory().post("/x/", data, format="multipart")
        force_authenticate(req, user=self.user)
        with mock.patch.object(mcm, "_scope", return_value=(self.school.id, None)), \
             mock.patch.object(mcm, "_admin", return_value=True):
            return mcm.migration_commit(req)

    def test_save_applies_corrections(self):
        resp = self.post("Admission No,First name,Surname,Class\n1004,David,,Grade 7 East\n",
                         {"2": {"last_name": "Mwangi"}})
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual(Student.objects.get().last_name, "Mwangi")

    def test_bad_corrections_rejected(self):
        resp = self.post("Admission No,First name,Surname,Class\n1004,David,Mwangi,Grade 7 East\n",
                         {"2": {"is_staff": "x"}})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Student.objects.count(), 0)
