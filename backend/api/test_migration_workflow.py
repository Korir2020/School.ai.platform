"""The migration workflow an administrator actually walks through.

Covers the parts added for the rebuilt Migration Centre: recognising unfamiliar
headings, choosing one class for the whole file, telling a genuine duplicate
apart from a learner who needs attention, re-checking without re-uploading the
file, bulk corrections and a safe retry after a dropped connection.
"""
import json
from datetime import date
from unittest import mock

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from api import migration_check as mck
from api import migration_commit as mcm
from api.migration_rules import analyse_upload
from api.test_migration_commit import make
from schools.models import (AcademicYear, ClassLevel, Curriculum, Enrollment,
                            MarkAuditLog, School, Stream, Student)

STRUCT = [
    {"id": 1, "name": "Grade 7", "level_number": 7,
     "streams": [{"id": 11, "name": "East"}, {"id": 12, "name": "West"}]},
    {"id": 2, "name": "Grade 10", "level_number": 10, "streams": [{"id": 21, "name": "East"}]},
]
HEAD = ["Admission No", "First name", "Surname", "Class"]


def by(res):
    return {r["row"]: r for r in res["rows"]}


def codes(row):
    return {i["code"] for i in row["issues"]}


class ColumnRecognitionTests(SimpleTestCase):
    def test_unfamiliar_headings_ask_for_a_mapping_instead_of_blocking(self):
        out = analyse_upload([["Kitambulisho", "Mtu", "Kundi"],
                              ["1001", "Amina Otieno", "Gredi 7"]], STRUCT)
        self.assertEqual(out["rows"], [])
        prompt = [n for n in out["needs_input"] if n["code"] == "mapping"][0]
        self.assertIn("name", prompt["missing"])
        self.assertEqual(out["headers"], ["Kitambulisho", "Mtu", "Kundi"])
        self.assertFalse([i for i in out["file_issues"] if i["severity"] == "block"])

    def test_manual_mapping_reads_the_columns(self):
        matrix = [["Namba", "Jina Kamili", "Darasa"],
                  ["1001", "Amina Otieno", "Grade 7 East"]]
        mapping = {"admission_number": 0, "full_name": 1, "class_level": 2}
        out = analyse_upload(matrix, STRUCT, mapping=mapping, name_order="first_last")
        row = out["rows"][0]
        self.assertEqual((row["admission_number"], row["first_name"], row["last_name"]),
                         ("1001", "Amina", "Otieno"))
        self.assertEqual(row["status"], "ready")
        self.assertEqual(out["mapping"]["class_level"], 2)

    def test_a_column_the_rules_did_not_know_can_be_mapped_by_hand(self):
        matrix = [["Index", "Name", "Class"], ["1001", "Amina Otieno", "Grade 7 East"]]
        out = analyse_upload(matrix, STRUCT, mapping={"admission_number": 0},
                             name_order="first_last")
        self.assertEqual(out["rows"][0]["admission_number"], "1001")
        self.assertEqual(out["rows"][0]["status"], "ready")

    def test_headings_can_be_typed_by_hand_when_the_file_has_none(self):
        matrix = [["1001", "Amina", "Otieno", "Grade 7 East"]]
        mapping = {"admission_number": 0, "first_name": 1, "last_name": 2, "class_level": 3}
        out = analyse_upload(matrix, STRUCT, mapping=mapping, header_row=-1)
        self.assertEqual(out["rows"][0]["status"], "ready")
        self.assertEqual(out["row_count"], 1)

    def test_swahili_headings_are_understood(self):
        matrix = [["Namba ya Kuingia", "Jina la Kwanza", "Jina la Ukoo", "Darasa"],
                  ["3001", "Samuel", "Kiptoo", "Grade 7 East"]]
        row = analyse_upload(matrix, STRUCT)["rows"][0]
        self.assertEqual((row["admission_number"], row["first_name"], row["last_name"]),
                         ("3001", "Samuel", "Kiptoo"))
        self.assertEqual(row["status"], "ready")

    def test_one_swahili_name_column_asks_which_name_comes_first(self):
        matrix = [["Namba ya Kuingia", "Jina Kamili", "Darasa"],
                  ["3001", "Samuel Kiptoo", "Grade 7 East"]]
        out = analyse_upload(matrix, STRUCT)
        self.assertEqual([n["code"] for n in out["needs_input"]], ["name_order"])
        out = analyse_upload(matrix, STRUCT, name_order="first_last")
        row = out["rows"][0]
        self.assertEqual((row["first_name"], row["last_name"]), ("Samuel", "Kiptoo"))
        self.assertEqual(row["class_label"], "Grade 7 East")

    def test_likely_heading_is_flagged_for_a_second_look(self):
        out = analyse_upload([["Admisson Number", "First name", "Surname", "Class"],
                              ["1001", "Amina", "Otieno", "Grade 7 East"]], STRUCT)
        self.assertTrue(out["mapping_uncertain"])
        self.assertEqual(out["mapping"]["admission_number"], 0)

    def test_columns_that_are_not_imported_are_named(self):
        out = analyse_upload([["Admission No", "First name", "Surname", "Class", "House"],
                              ["1001", "Amina", "Otieno", "Grade 7 East", "Nyati"]], STRUCT)
        self.assertEqual([u["label"] for u in out["unknown_columns"]], ["House"])
        self.assertIn("House", [i["message"] for i in out["file_issues"] if i["code"] == "ignored_columns"][0])

    def test_sample_values_come_back_with_the_headings(self):
        out = analyse_upload([["Admission No", "First name", "Surname", "Class"],
                              ["1001", "Amina", "Otieno", "Grade 7 East"],
                              ["1002", "Brian", "Kamau", "Grade 7 East"]], STRUCT)
        col = [c for c in out["columns"] if c["field"] == "first_name"][0]
        self.assertEqual(col["samples"], ["Amina", "Brian"])


class DefaultClassTests(SimpleTestCase):
    def test_one_class_for_the_whole_file(self):
        out = analyse_upload([["Admission No", "First name", "Surname"],
                              ["1001", "Amina", "Otieno"],
                              ["1002", "Brian", "Kamau"]], STRUCT, default_class="Grade 7 East")
        self.assertEqual([r["status"] for r in out["rows"]], ["ready", "ready"])
        self.assertEqual([r["class_label"] for r in out["rows"]], ["Grade 7 East"] * 2)
        self.assertEqual(out["summary"]["by_class"], {"Grade 7 East": 2})

    def test_a_class_that_does_not_exist_is_refused(self):
        out = analyse_upload([["Admission No", "First name", "Surname"],
                              ["1001", "Amina", "Otieno"]], STRUCT, default_class="Grade 12")
        self.assertEqual(out["rows"], [])
        self.assertTrue(any(i["code"] == "default_class_invalid" for i in out["file_issues"]))

    def test_blank_class_cell_falls_back_to_the_chosen_class(self):
        out = analyse_upload([["Admission No", "First name", "Surname", "Class"],
                              ["1001", "Amina", "Otieno", ""]], STRUCT, default_class="Grade 7 West")
        self.assertEqual(out["rows"][0]["class_label"], "Grade 7 West")
        self.assertIn("default_class_used", codes(out["rows"][0]))

    def test_a_file_without_a_class_column_asks_for_one_class_not_for_columns(self):
        matrix = [["Admission No", "First name", "Surname"],
                  ["1001", "Amina", "Otieno"]]
        out = analyse_upload(matrix, STRUCT)
        self.assertFalse([n for n in out["needs_input"] if n["code"] == "mapping"])
        self.assertEqual(out["rows"][0]["status"], "blocked")
        self.assertIn("class_missing", codes(out["rows"][0]))
        out = analyse_upload(matrix, STRUCT, default_class="Grade 7 West")
        self.assertEqual(out["rows"][0]["status"], "ready")
        self.assertEqual(out["rows"][0]["class_label"], "Grade 7 West")

    def test_without_a_default_a_blank_class_still_blocks(self):
        out = analyse_upload([["Admission No", "First name", "Surname", "Class"],
                              ["1001", "Amina", "Otieno", ""]], STRUCT)
        self.assertEqual(out["rows"][0]["status"], "blocked")
        self.assertIn("class_missing", codes(out["rows"][0]))


class DuplicateTests(SimpleTestCase):
    def test_learner_already_in_marian_is_skipped_not_blocked(self):
        existing = [{"admission_number": "A1", "first_name": "Jane", "last_name": "Otieno"}]
        out = analyse_upload([HEAD, ["a1", "Jane", "Otieno", "Grade 7 East"]], STRUCT, existing=existing)
        self.assertEqual(out["rows"][0]["status"], "duplicate")
        self.assertEqual(out["summary"]["duplicates"], 1)
        self.assertEqual(out["summary"]["ready"], 0)
        self.assertEqual(out["summary"]["skipped"], 1)

    def test_changing_the_admission_number_makes_the_row_importable(self):
        existing = [{"admission_number": "A1", "first_name": "Jane", "last_name": "Otieno"}]
        matrix = [HEAD, ["A1", "Jane", "Otieno", "Grade 7 East"]]
        out = analyse_upload(matrix, STRUCT, existing=existing, fixes={2: {"admission_number": "A9"}})
        # Same name as the learner already in Marian, so it asks once before adding.
        self.assertEqual(out["rows"][0]["status"], "needs_confirmation")
        out = analyse_upload(matrix, STRUCT, existing=existing,
                             fixes={2: {"admission_number": "A9"}},
                             confirmations={2: ["same_name_existing"]})
        self.assertEqual(out["rows"][0]["status"], "ready")

    def test_two_rows_with_one_admission_number_are_still_an_error(self):
        out = analyse_upload([HEAD, ["A1", "Jane", "Otieno", "Grade 7 East"],
                              ["a1", "Ann", "Kamau", "Grade 7 West"]], STRUCT)
        self.assertEqual([r["status"] for r in out["rows"]], ["blocked", "blocked"])

    def test_similar_names_only_ask_in_a_handwritten_file(self):
        matrix = [HEAD, ["A1", "Jane", "Otieno", "Grade 7 East"],
                  ["A2", "Jane", "Otienoo", "Grade 7 West"]]
        self.assertEqual([r["status"] for r in analyse_upload(matrix, STRUCT)["rows"]], ["ready", "ready"])
        self.assertEqual([r["status"] for r in analyse_upload(matrix, STRUCT, source="paper")["rows"]],
                         ["needs_confirmation"] * 2)


class CorrectionTests(SimpleTestCase):
    def test_bulk_class_correction_fixes_every_row_at_once(self):
        matrix = [HEAD] + [["A%d" % n, "L%d" % n, "Surname", "Grade 99"] for n in range(1, 6)]
        self.assertEqual({r["status"] for r in analyse_upload(matrix, STRUCT)["rows"]}, {"blocked"})
        fixes = {n: {"class_level": "Grade 7 East"} for n in range(2, 7)}
        out = analyse_upload(matrix, STRUCT, fixes=fixes)
        self.assertEqual({r["status"] for r in out["rows"]}, {"ready"})
        self.assertEqual(out["summary"]["by_class"], {"Grade 7 East": 5})

    def test_a_grade_ten_learner_needs_an_assessment_number(self):
        matrix = [HEAD + ["Assessment No"],
                  ["A1", "Jane", "Otieno", "Grade 10 East", ""]]
        out = analyse_upload(matrix, STRUCT)
        self.assertEqual(out["rows"][0]["status"], "blocked")
        self.assertIn("assessment_missing", codes(out["rows"][0]))
        fixed = analyse_upload(matrix, STRUCT, fixes={2: {"assessment_number": "AS-77"}})
        self.assertEqual(fixed["rows"][0]["status"], "ready")

    def test_unknown_class_suggests_the_real_ones(self):
        row = analyse_upload([HEAD, ["A1", "Jane", "Otieno", "Grade 8 East"]], STRUCT)["rows"][0]
        self.assertIn("Grade 7", " ".join(row["suggestions"]["class_level"]))

    def test_confirmations_can_be_accepted_for_every_row_at_once(self):
        matrix = [HEAD, ["", "Jane", "Otieno", "Grade 7 East"], ["", "Ann", "Kamau", "Grade 7 West"]]
        self.assertEqual({r["status"] for r in analyse_upload(matrix, STRUCT)["rows"]}, {"needs_confirmation"})
        out = analyse_upload(matrix, STRUCT, confirmations={"all": ["missing_admission"]})
        self.assertEqual({r["status"] for r in out["rows"]}, {"ready"})
        self.assertEqual(out["summary"]["temporary_admission"], 2)


class _Base(TestCase):
    def setUp(self):
        self.school = make(School, name="Test School")
        self.user = User.objects.create(username="admin")
        cur = make(Curriculum, name="Test")
        self.g7 = make(ClassLevel, curriculum=cur, name="Grade 7", level_number=7)
        self.g10 = make(ClassLevel, curriculum=cur, name="Grade 10", level_number=10)
        make(Stream, school=self.school, class_level=self.g7, name="East")
        make(Stream, school=self.school, class_level=self.g10, name="East (Grade 10)")
        self.year = make(AcademicYear, school=self.school, name="2026",
                         start_date=date(2026, 1, 1), end_date=date(2026, 12, 1), is_active=True)

    def check(self, data):
        req = APIRequestFactory().post("/x/", data, format="multipart")
        force_authenticate(req, user=self.user)
        with mock.patch.object(mck, "_scope", return_value=(self.school.id, None)), \
             mock.patch.object(mck, "_admin", return_value=True):
            return mck.migration_check(req)

    def commit(self, data):
        req = APIRequestFactory().post("/x/", data, format="multipart")
        force_authenticate(req, user=self.user)
        with mock.patch.object(mcm, "_scope", return_value=(self.school.id, None)), \
             mock.patch.object(mcm, "_admin", return_value=True):
            return mcm.migration_commit(req)


class CheckEndpointTests(_Base):
    def test_the_table_comes_back_so_the_file_is_not_uploaded_again(self):
        resp = self.check({"file": SimpleUploadedFile(
            "a.csv", ("Admission No,First name,Surname,Class\n1001,Amina,Otieno,Grade 7 East\n").encode())})
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["matrix"][1][0], "1001")
        again = self.check({"matrix": json.dumps(resp.data["matrix"])})
        self.assertEqual(again.status_code, 200, again.data)
        self.assertEqual(again.data["summary"]["total"], 1)

    def test_default_class_is_honoured_by_the_endpoint(self):
        csv = "Admission No,First name,Surname\n1001,Amina,Otieno\n"
        resp = self.check({"file": SimpleUploadedFile("a.csv", csv.encode()),
                           "default_class": "Grade 7 East"})
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["summary"]["ready"], 1)
        self.assertEqual(resp.data["rows"][0]["class_label"], "Grade 7 East")

    def test_mapping_is_honoured_by_the_endpoint(self):
        csv = "Kitambulisho,Mtu,Kundi\n1001,Amina Otieno,Grade 7 East\n"
        resp = self.check({"file": SimpleUploadedFile("a.csv", csv.encode())})
        self.assertEqual(resp.data["needs_input"][0]["code"], "mapping")
        resp = self.check({"file": SimpleUploadedFile("a.csv", csv.encode()),
                           "mapping": json.dumps({"admission_number": 0, "full_name": 1,
                                                  "class_level": 2}),
                           "name_order": "first_last"})
        self.assertEqual(resp.data["summary"]["ready"], 1, resp.data)
        self.assertEqual(resp.data["rows"][0]["last_name"], "Otieno")

    def test_unsupported_file_explains_what_to_do(self):
        resp = self.check({"file": SimpleUploadedFile("a.docx", b"PK\x03\x04binary")})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Excel", resp.data["detail"])

    def test_old_excel_file_explains_what_to_do(self):
        resp = self.check({"file": SimpleUploadedFile("a.xls", b"\xd0\xcf\x11\xe0")})
        self.assertEqual(resp.status_code, 400)
        self.assertIn(".xlsx", resp.data["detail"])

    def test_bad_mapping_is_rejected_cleanly(self):
        resp = self.check({"file": SimpleUploadedFile("a.csv", b"Name,Class\nA B,Grade 7\n"),
                           "mapping": "{not json"})
        self.assertEqual(resp.status_code, 400)


class CommitWorkflowTests(_Base):
    def test_import_with_a_default_class_and_a_mapping(self):
        csv = "Namba,Jina\n1001,Amina Otieno\n1002,Brian Kamau\n"
        data = {"file": SimpleUploadedFile("a.csv", csv.encode()),
                "mapping": json.dumps({"admission_number": 0, "full_name": 1}),
                "name_order": "last_first", "default_class": "Grade 7 East"}
        resp = self.commit(data)
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual(resp.data["created"], 2)
        self.assertEqual(Student.objects.count(), 2)
        self.assertEqual(Enrollment.objects.count(), 2)

    def test_partial_import_leaves_the_rest_for_a_second_pass(self):
        csv = ("Admission No,First name,Surname,Class\n"
               "1001,Amina,Otieno,Grade 7 East\n"
               "1002,Brian,Kamau,Grade 99\n")
        first = self.commit({"file": SimpleUploadedFile("a.csv", csv.encode())})
        self.assertEqual((first.data["created"], first.data["skipped"]), (1, 1))
        self.assertEqual(Student.objects.count(), 1)
        second = self.check({"file": SimpleUploadedFile("a.csv", csv.encode())})
        self.assertEqual(second.data["summary"]["duplicates"], 1)
        self.assertEqual(second.data["summary"]["blocked"], 1)

    def test_repeating_the_same_request_does_not_add_learners_twice(self):
        csv = "Admission No,First name,Surname,Class\n1001,Amina,Otieno,Grade 7 East\n"
        def payload():
            return {"file": SimpleUploadedFile("a.csv", csv.encode()), "request_id": "req-12345678"}
        first = self.commit(payload())
        self.assertEqual(first.status_code, 201)
        again = self.commit(payload())
        self.assertEqual(again.status_code, 200, again.data)
        self.assertTrue(again.data["already_saved"])
        self.assertEqual(again.data["created"], 1)
        self.assertEqual(Student.objects.count(), 1)
        self.assertEqual(MarkAuditLog.objects.filter(action="student_migration_import").count(), 1)

    def test_a_second_import_of_the_same_file_adds_nothing(self):
        csv = "Admission No,First name,Surname,Class\n1001,Amina,Otieno,Grade 7 East\n"
        self.commit({"file": SimpleUploadedFile("a.csv", csv.encode()), "request_id": "req-aaaaaaaa"})
        resp = self.commit({"file": SimpleUploadedFile("a.csv", csv.encode()), "request_id": "req-bbbbbbbb"})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Student.objects.count(), 1)

    def test_a_bad_request_id_is_refused(self):
        csv = "Admission No,First name,Surname,Class\n1001,Amina,Otieno,Grade 7 East\n"
        resp = self.commit({"file": SimpleUploadedFile("a.csv", csv.encode()), "request_id": "x"})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Student.objects.count(), 0)

    def test_commit_accepts_the_table_sent_back_by_the_browser(self):
        csv = "Admission No,First name,Surname,Class\n1001,Amina,Otieno,Grade 7 East\n"
        checked = self.check({"file": SimpleUploadedFile("a.csv", csv.encode())})
        resp = self.commit({"matrix": json.dumps(checked.data["matrix"]), "request_id": "req-cccccccc"})
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual(Student.objects.count(), 1)

    def test_audit_records_what_was_added_and_where(self):
        csv = ("Admission No,First name,Surname,Class\n"
               "1001,Amina,Otieno,Grade 7 East\n1002,Brian,Kamau,Grade 7 East\n")
        self.commit({"file": SimpleUploadedFile("a.csv", csv.encode()), "request_id": "req-dddddddd"})
        log = MarkAuditLog.objects.get(action="student_migration_import")
        self.assertEqual(log.details["added"], 2)
        self.assertEqual(log.details["classes"], {"Grade 7 East": 2})
        self.assertEqual(log.details["request_id"], "req-dddddddd")

    def test_a_learner_without_an_assessment_number_is_not_imported_silently(self):
        csv = "Admission No,First name,Surname,Class\n2001,Zawadi,Mwangi,Grade 10 East (Grade 10)\n"
        resp = self.commit({"file": SimpleUploadedFile("a.csv", csv.encode())})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Student.objects.count(), 0)


class ReviewListTests(SimpleTestCase):
    """What the review list asks, and what it stops asking once decided."""

    def test_a_decision_already_taken_is_not_asked_again(self):
        out = analyse_upload([HEAD, ["", "Jane", "Otieno", "Grade 7 East"]], STRUCT,
                             confirmations={2: ["missing_admission"]})
        row = out["rows"][0]
        self.assertEqual(row["status"], "ready")
        self.assertFalse([i for i in row["issues"] if i["severity"] in ("confirm", "block")])
        self.assertTrue(row["provisional_admission"])

    def test_a_learner_already_in_marian_is_not_asked_to_confirm(self):
        existing = [{"admission_number": "A1", "first_name": "Jane", "last_name": "Otieno"}]
        out = analyse_upload([HEAD, ["A1", "Jane", "Otieno", "Grade 7 East"]], STRUCT, existing=existing)
        row = out["rows"][0]
        self.assertEqual(row["status"], "duplicate")
        self.assertFalse([i for i in row["issues"] if i["severity"] == "confirm"])

    def test_only_ready_learners_are_counted_for_the_class_breakdown(self):
        matrix = [HEAD + ["Assessment No"],
                  ["A1", "Jane", "Otieno", "Grade 10 East", ""],
                  ["A2", "Ann", "Kamau", "Grade 7 East", ""]]
        out = analyse_upload(matrix, STRUCT)
        self.assertEqual(out["summary"]["by_class"], {"Grade 10 East": 1, "Grade 7 East": 1})
        self.assertEqual(out["summary"]["by_class_ready"], {"Grade 7 East": 1})

    def test_running_the_same_file_twice_does_not_add_a_learner_without_a_number(self):
        existing = [{"admission_number": "NO-ADM-0001", "first_name": "Daniel", "last_name": "Wafula"}]
        out = analyse_upload([HEAD, ["", "Daniel", "Wafula", "Grade 7 East"]], STRUCT, existing=existing)
        row = out["rows"][0]
        self.assertEqual(row["status"], "duplicate")
        self.assertNotIn("missing_admission", codes(row))
        self.assertEqual(out["summary"]["ready"], 0)

    def test_a_different_learner_without_a_number_is_still_imported(self):
        existing = [{"admission_number": "NO-ADM-0001", "first_name": "Daniel", "last_name": "Wafula"}]
        out = analyse_upload([HEAD, ["", "Grace", "Achieng", "Grade 7 East"]], STRUCT,
                             existing=existing, confirmations={2: ["missing_admission"]})
        self.assertEqual(out["rows"][0]["status"], "ready")


class StructureTests(TestCase):
    def test_a_class_with_no_streams_and_no_learners_can_still_be_used(self):
        school = make(School, name="Structure School", code="STRUCT1")
        curriculum = make(Curriculum, name="Structure curriculum", code="STRUCT")
        make(ClassLevel, curriculum=curriculum, name="Grade 11", level_number=11)
        names = [level["name"] for level in mck.build_structure(school.id)]
        self.assertIn("Grade 11", names)

    def test_streams_set_up_for_the_school_come_back_with_their_class(self):
        school = make(School, name="Stream School", code="STRUCT2")
        curriculum = make(Curriculum, name="Stream curriculum", code="STRUCTS")
        level = make(ClassLevel, curriculum=curriculum, name="Grade 9", level_number=9)
        make(Stream, school=school, class_level=level, name="Blue")
        found = [l for l in mck.build_structure(school.id) if l["name"] == "Grade 9"][0]
        self.assertEqual([s["name"] for s in found["streams"]], ["Blue"])
