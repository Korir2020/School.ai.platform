import contextlib
import json
import urllib.error
from unittest import mock

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from api import migration_photos as mp
from api.migration_check import parse_table
from api.migration_rules import CHECK_OPEN, UNREADABLE, analyse_upload
from api.test_migration_commit import make
from schools.models import MarkAuditLog, School

STRUCT = [{"id": 1, "name": "Grade 7", "level_number": 7, "streams": [{"id": 11, "name": "East"}]}]
HEAD = ["Admission No", "First name", "Surname", "Class"]
JPG = b"\xff\xd8\xff" + b"0" * 100


def reply(rows, headers=HEAD, notes="", stop="end_turn"):
    body = {"headers": headers, "rows": rows}
    if notes:
        body["notes"] = notes
    return {"stop_reason": stop, "content": [{"type": "text", "text": json.dumps(body)}]}


class PhotoParseTests(SimpleTestCase):
    def test_markers_counted(self):
        out = mp.parse_page(reply([["1001", "Amina", "[UNREADABLE]", "Grade 7 East"],
                                   ["1002", "[CHECK:Brian]", "Kamau", "Grade 7 East"]]), 1)
        self.assertEqual((out["unreadable"], out["to_check"]), (1, 1))
        self.assertEqual(out["rows"][0][2], UNREADABLE)
        self.assertEqual(out["rows"][1][1], CHECK_OPEN + "Brian]")

    def test_marker_variants_normalised(self):
        out = mp.parse_page(reply([["1001", "[unreadable]", "[check: Otieno ]", "[CHECK:]"]]), 1)
        self.assertEqual(out["rows"][0][1:], [UNREADABLE, CHECK_OPEN + "Otieno]", UNREADABLE])

    def test_short_row_padded_with_unreadable(self):
        out = mp.parse_page(reply([["1001", "Amina"]]), 1)
        self.assertEqual(out["rows"][0], ["1001", "Amina", UNREADABLE, UNREADABLE])

    def test_long_row_refused(self):
        with self.assertRaises(mp.PhotoError):
            mp.parse_page(reply([["1", "a", "b", "c", "d"]]), 1)

    def test_cut_off_reply_refused(self):
        with self.assertRaises(mp.PhotoError) as ctx:
            mp.parse_page(reply([["1", "a", "b", "c"]], stop="max_tokens"), 2)
        self.assertIn("Page 2", str(ctx.exception))

    def test_bad_json_refused(self):
        with self.assertRaises(mp.PhotoError):
            mp.parse_page({"stop_reason": "end_turn", "content": [{"type": "text", "text": "sorry"}]}, 1)

    def test_no_rows_refused(self):
        with self.assertRaises(mp.PhotoError):
            mp.parse_page(reply([]), 1)

    def test_later_page_uses_known_headers(self):
        out = mp.parse_page(reply([["1003", "Cate", "Wanjiru", "Grade 7 East"]], headers=["x"]), 2, known_headers=HEAD)
        self.assertEqual(out["headers"], HEAD)


class MarkerRuleTests(SimpleTestCase):
    def by(self, res):
        return {r["row"]: r for r in res["rows"]}

    def test_unreadable_cell_blocks_until_typed(self):
        m = [HEAD, ["1004", "David", UNREADABLE, "Grade 7 East"]]
        row = self.by(analyse_upload(m, STRUCT))[2]
        self.assertEqual(row["status"], "blocked")
        self.assertIn("unreadable_cell", [i["code"] for i in row["issues"]])
        fixed = self.by(analyse_upload(m, STRUCT, fixes={2: {"last_name": "Mwangi"}}))[2]
        self.assertEqual(fixed["status"], "ready")

    def test_check_cell_needs_confirmation(self):
        m = [HEAD, ["1005", CHECK_OPEN + "Amina]", "Otieno", "Grade 7 East"]]
        row = self.by(analyse_upload(m, STRUCT))[2]
        self.assertEqual((row["status"], row["first_name"]), ("needs_confirmation", "Amina"))
        done = self.by(analyse_upload(m, STRUCT, confirmations={2: ["check_reading_first_name"]}))[2]
        self.assertEqual(done["status"], "ready")

    def test_unreadable_class_blocks(self):
        m = [HEAD, ["1006", "Faith", "Wanjiru", UNREADABLE]]
        self.assertEqual(self.by(analyse_upload(m, STRUCT))[2]["status"], "blocked")

    def test_fully_unreadable_line_is_kept(self):
        m = [HEAD, [UNREADABLE] * 4, ["1007", "Joy", "Ali", "Grade 7 East"]]
        res = analyse_upload(m, STRUCT)
        self.assertEqual(res["summary"]["total"], 2)
        self.assertEqual(self.by(res)[2]["status"], "blocked")


class PhotoViewTests(TestCase):
    def setUp(self):
        self.school = make(School, name="Test School")
        self.user = User.objects.create(username="admin")

    def photo(self, data=JPG, name="p.jpg"):
        return {"photo": SimpleUploadedFile(name, data), "page": "1"}

    def call(self, method="post", data=None, admin=True, key="k", **api):
        factory = APIRequestFactory()
        req = factory.get("/x/") if method == "get" else factory.post("/x/", data or {}, format="multipart")
        force_authenticate(req, user=self.user)
        api = api or {"side_effect": AssertionError("the service must not be called")}
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(mp, "_scope", return_value=(self.school.id, None)))
            stack.enter_context(mock.patch.object(mp, "_admin", return_value=admin))
            stack.enter_context(mock.patch.object(mp, "_api_key", return_value=key))
            self.api_mock = stack.enter_context(mock.patch.object(mp, "_call_api", **api))
            return mp.migration_read_photo(req)

    def test_status_off_and_on(self):
        self.assertIs(self.call("get", key="").data["enabled"], False)
        self.assertIs(self.call("get", key="k").data["enabled"], True)

    def test_off_means_clear_message_and_no_call(self):
        resp = self.call(data=self.photo(), key="")
        self.assertEqual(resp.status_code, 503)
        self.assertFalse(resp.data["enabled"])
        self.api_mock.assert_not_called()

    def test_read_ok_and_logged(self):
        resp = self.call(data=self.photo(), return_value=reply([["1001", "Amina", "[UNREADABLE]", "Grade 7 East"]]))
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual((resp.data["unreadable"], len(resp.data["rows"])), (1, 1))
        entry = MarkAuditLog.objects.get(action=mp.AUDIT_ACTION)
        self.assertEqual((entry.details["status"], entry.details["pages"]), ("read", 1))

    def test_not_an_image_refused(self):
        resp = self.call(data=self.photo(b"hello", "p.jpg"))
        self.assertEqual(resp.status_code, 400)
        self.api_mock.assert_not_called()

    def test_daily_limit(self):
        MarkAuditLog.objects.create(school_id=self.school.id, user=self.user, action=mp.AUDIT_ACTION, details={"pages": 40})
        with mock.patch.object(mp, "_daily_cap", return_value=40):
            resp = self.call(data=self.photo())
        self.assertEqual(resp.status_code, 429)
        self.api_mock.assert_not_called()

    def test_service_error_is_reported_not_hidden(self):
        err = urllib.error.HTTPError("https://x", 429, "busy", {}, None)
        resp = self.call(data=self.photo(), side_effect=err)
        self.assertEqual(resp.status_code, 502)
        self.assertIn("Page 1", resp.data["detail"])
        self.assertEqual(MarkAuditLog.objects.get(action=mp.AUDIT_ACTION).details["status"], "failed")

    def test_non_admin_forbidden(self):
        resp = self.call(data=self.photo(), admin=False)
        self.assertEqual(resp.status_code, 403)
        self.api_mock.assert_not_called()

    def test_photo_output_flows_through_the_rules(self):
        resp = self.call(data=self.photo(), return_value=reply([
            ["1001", "Amina", "Otieno", "Grade 7 East"],
            ["1002", "Brian", "[UNREADABLE]", "Grade 7 East"],
            ["1003", "[CHECK:Cate]", "Wanjiru", "Grade 7 East"]]))
        text = "\n".join("\t".join(r) for r in [resp.data["headers"]] + resp.data["rows"])
        res = analyse_upload(parse_table(text=text), STRUCT)
        self.assertEqual([r["status"] for r in res["rows"]], ["ready", "blocked", "needs_confirmation"])
