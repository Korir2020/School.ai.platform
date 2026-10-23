import io
from unittest import mock

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from api import migration_check as mc

STRUCT = [{"id": 1, "name": "Grade 7", "level_number": 7, "streams": [{"id": 11, "name": "East"}]}]
HEAD = ["Admission No", "First name", "Surname", "Class"]
CSV = "Admission No,First name,Surname,Class\n1001,Amina,Otieno,Grade 7 East\n"


def _post(data, admin=True, scope=(5, None)):
    req = APIRequestFactory().post("/x/", data, format="multipart")
    force_authenticate(req, user=User.objects.get_or_create(username="t")[0])
    with mock.patch.object(mc, "_scope", return_value=scope), \
         mock.patch.object(mc, "_admin", return_value=admin), \
         mock.patch.object(mc, "build_structure", return_value=STRUCT) as bs, \
         mock.patch.object(mc, "build_existing", return_value=[]):
        return mc.migration_check(req), bs


class ParseTests(SimpleTestCase):
    def test_csv(self):
        rows = mc.parse_table(SimpleUploadedFile("a.csv", CSV.encode()))
        self.assertEqual(rows[0], HEAD)
        self.assertEqual(len(rows), 2)

    def test_pasted_tab_text(self):
        rows = mc.parse_table(text="Admission No\tFirst name\tSurname\tClass\n1001\tAmina\tOtieno\tGrade 7 East")
        self.assertEqual(rows[0], HEAD)
        self.assertEqual(rows[1][1], "Amina")

    def test_cp1252_csv(self):
        rows = mc.parse_table(SimpleUploadedFile("a.csv", "Name,Class\nZoë,Grade 7".encode("cp1252")))
        self.assertEqual(rows[1][0], "Zoë")

    def test_xlsx_numbers_become_clean_text(self):
        from openpyxl import Workbook
        wb = Workbook()
        wb.active.append(HEAD)
        wb.active.append([1001, "Amina", "Otieno", "Grade 7 East"])
        wb.active.append([1002.0, "Brian", "Kamau", "Grade 7 East"])
        buf = io.BytesIO()
        wb.save(buf)
        rows = mc.parse_table(SimpleUploadedFile("a.xlsx", buf.getvalue()))
        self.assertEqual([rows[1][0], rows[2][0]], ["1001", "1002"])

    def test_old_xls_rejected(self):
        with self.assertRaises(mc.UploadError):
            mc.parse_table(SimpleUploadedFile("a.xls", b"x"))

    def test_confirmation_keys(self):
        self.assertEqual(mc._confirmations('{"3": ["a"], "all": ["b"]}'), {3: ["a"], "all": ["b"]})

    def test_confirmation_bad(self):
        with self.assertRaises(mc.UploadError):
            mc._confirmations("not json")


class ViewTests(TestCase):
    def test_check_ok_and_saves_nothing(self):
        resp, bs = _post({"file": SimpleUploadedFile("a.csv", CSV.encode())})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["summary"]["total"], 1)
        self.assertIs(resp.data["committed"], False)
        bs.assert_called_once_with(5)

    def test_non_admin_blocked(self):
        with mock.patch.object(mc, "analyse_upload") as engine:
            resp, _ = _post({"file": SimpleUploadedFile("a.csv", CSV.encode())}, admin=False)
        self.assertEqual(resp.status_code, 403)
        engine.assert_not_called()

    def test_posted_school_ignored_for_school_admin(self):
        resp, bs = _post({"file": SimpleUploadedFile("a.csv", CSV.encode()), "school_id": "99"})
        self.assertEqual(resp.status_code, 200)
        bs.assert_called_once_with(5)

    def test_missing_file(self):
        resp, _ = _post({})
        self.assertEqual(resp.status_code, 400)

    def test_superuser_must_choose_school(self):
        resp, _ = _post({"file": SimpleUploadedFile("a.csv", CSV.encode())}, scope=(None, None))
        self.assertEqual(resp.status_code, 400)
