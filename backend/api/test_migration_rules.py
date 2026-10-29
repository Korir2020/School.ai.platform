from django.test import SimpleTestCase

from .migration_rules import analyse_upload, detect_header_row, natural_key

STRUCTURE = [
    {"id": 1, "name": "Grade 9", "level_number": 9, "streams": [{"id": 11, "name": "East"}, {"id": 12, "name": "West"}]},
    {"id": 2, "name": "Grade 10", "level_number": 10, "streams": [{"id": 21, "name": "East"}, {"id": 22, "name": "West"}]},
    {"id": 3, "name": "Grade 11", "level_number": 11, "streams": []},
]
HEAD = ["Adm No", "First Name", "Surname", "Grade", "Stream", "Assessment No"]


def run(rows, head=HEAD, **kw):
    return analyse_upload([head] + rows, STRUCTURE, **kw)


def codes(row):
    return {i["code"] for i in row["issues"]}


class MigrationRulesTests(SimpleTestCase):
    def test_title_rows_above_header_are_skipped(self):
        matrix = [["ABC School learners"], [], HEAD, ["A1", "Jane", "Otieno", "Grade 9", "East", ""]]
        self.assertEqual(detect_header_row(matrix), 2)
        out = analyse_upload(matrix, STRUCTURE)
        self.assertEqual(out["rows"][0]["status"], "ready")

    def test_missing_admission_needs_confirmation_then_gets_marked_number(self):
        rows = [["", "Jane", "Otieno", "Grade 9", "East", ""]]
        out = run(rows)
        self.assertEqual(out["rows"][0]["status"], "needs_confirmation")
        out = run(rows, confirmations={"all": ["missing_admission"]})
        r = out["rows"][0]
        self.assertEqual(r["status"], "ready")
        self.assertEqual(r["admission_number"], "NO-ADM-0001")
        self.assertTrue(r["provisional_admission"])

    def test_same_name_different_admission_needs_confirmation(self):
        rows = [["A1", "Jane", "Otieno", "Grade 9", "East", ""], ["A2", "Otieno", "Jane", "Grade 9", "West", ""]]
        out = run(rows)
        self.assertEqual([r["status"] for r in out["rows"]], ["needs_confirmation"] * 2)
        out = run(rows, confirmations={"all": ["same_name"]})
        self.assertEqual([r["status"] for r in out["rows"]], ["ready"] * 2)

    def test_same_admission_is_blocked_on_both_rows(self):
        rows = [["A1", "Jane", "Otieno", "Grade 9", "East", ""], ["a1", "Ann", "Kamau", "Grade 9", "West", ""]]
        out = run(rows)
        self.assertEqual([r["status"] for r in out["rows"]], ["blocked", "blocked"])

    def test_grade_10_needs_assessment_number_grade_9_does_not(self):
        rows = [["A1", "Jane", "Otieno", "Grade 10", "East", ""], ["A2", "Ann", "Kamau", "Grade 9", "East", ""],
                ["A3", "Eve", "Mwangi", "Grade 10", "West", "AS-5"]]
        out = {r["row"]: r for r in run(rows)["rows"]}
        self.assertIn("assessment_missing", codes(out[2]))
        self.assertEqual(out[3]["status"], "ready")
        self.assertEqual(out[4]["status"], "ready")

    def test_mixed_classes_are_placed_and_sorted_ascending(self):
        rows = [["A10", "Zed", "One", "Grade 10", "West", "X2"], ["A2", "Amy", "Two", "Grade 9", "East", ""],
                ["A1", "Bob", "Three", "Grade 9", "East", ""], ["A3", "Cy", "Four", "Grade 10", "East", "X1"]]
        out = run(rows)
        self.assertEqual(out["sorted_by"], "admission_number")
        self.assertEqual([r["admission_number"] for r in out["rows"]], ["A1", "A2", "A3", "A10"])
        self.assertEqual([r["class_label"] for r in out["rows"]], ["Grade 9 East", "Grade 9 East", "Grade 10 East", "Grade 10 West"])

    def test_class_not_found_names_the_closest_classes(self):
        r = run([["A1", "Jane", "Otieno", "Grade 8", "East", ""]])["rows"][0]
        msg = [i["message"] for i in r["issues"] if i["code"] == "class_not_found"][0]
        self.assertIn("Closest in this school", msg)

    def test_class_not_found_lists_all_classes_when_none_is_close(self):
        r = run([["A1", "Jane", "Otieno", "Form 4", "", ""]])["rows"][0]
        self.assertEqual(r["status"], "blocked")
        msg = [i["message"] for i in r["issues"] if i["code"] == "class_not_found"][0]
        self.assertIn("Classes in this school", msg)
        self.assertIn("Grade 9", msg)
        self.assertIn("Grade 11", msg)

    def test_class_not_found_when_school_has_no_classes(self):
        out = analyse_upload([HEAD, ["A1", "Jane", "Otieno", "Form 4", "", ""]], [])
        r = out["rows"][0]
        msg = [i["message"] for i in r["issues"] if i["code"] == "class_not_found"][0]
        self.assertIn("no classes yet", msg)

    def test_unknown_class_is_blocked_and_never_guessed(self):
        out = run([["A1", "Jane", "Otieno", "Grade 8", "East", ""]])
        r = out["rows"][0]
        self.assertEqual(r["status"], "blocked")
        self.assertIn("class_not_found", codes(r))
        self.assertIsNone(r["level_id"])

    def test_class_and_stream_in_one_cell_is_read_with_a_notice(self):
        r = run([["A1", "Jane", "Otieno", "Grade 10 East", "", "X1"]])["rows"][0]
        self.assertEqual(r["status"], "ready")
        self.assertEqual(r["class_label"], "Grade 10 East")
        self.assertIn("class_split", codes(r))

    def test_level_without_stream_column_does_not_crash(self):
        r = run([["A1", "Jane", "Otieno", "Grade 11", "", "X1"]])["rows"][0]
        self.assertEqual(r["status"], "ready")
        self.assertIsNone(r["stream_id"])

    def test_one_name_column_asks_which_order_first(self):
        head = ["Adm No", "Name", "Class"]
        out = analyse_upload([head, ["A1", "Jane Akinyi Otieno", "Grade 9 East"]], STRUCTURE)
        self.assertEqual(out["needs_input"][0]["code"], "name_order")
        out = analyse_upload([head, ["A1", "Otieno Jane", "Grade 9 East"]], STRUCTURE, name_order="last_first")
        r = out["rows"][0]
        self.assertEqual((r["first_name"], r["last_name"]), ("Jane", "Otieno"))

    def test_other_names_is_never_used_as_surname(self):
        head = ["Adm No", "First Name", "Other Names", "Surname", "Grade", "Stream"]
        r = analyse_upload([head, ["A1", "Jane", "Akinyi", "Otieno", "Grade 9", "East"]], STRUCTURE)["rows"][0]
        self.assertEqual((r["first_name"], r["last_name"]), ("Jane Akinyi", "Otieno"))

    def test_two_name_columns_stop_the_file(self):
        out = analyse_upload([["Name", "Names", "Grade"], ["Jane Otieno", "x", "Grade 9"]], STRUCTURE)
        self.assertTrue(any(i["code"] == "ambiguous_columns" for i in out["file_issues"]))
        self.assertEqual(out["rows"], [])

    def test_existing_student_blocks_same_admission_and_asks_about_same_name(self):
        existing = [{"admission_number": "A1", "first_name": "Jane", "last_name": "Otieno"}]
        rows = [["a1", "Ann", "Kamau", "Grade 9", "East", ""], ["B7", "Jane", "Otieno", "Grade 9", "West", ""]]
        out = {r["row"]: r for r in run(rows, existing=existing)["rows"]}
        self.assertEqual(out[2]["status"], "blocked")
        self.assertEqual(out[3]["status"], "needs_confirmation")

    def test_handwritten_similar_name_asks_but_typed_file_does_not(self):
        rows = [["A1", "Jane", "Otieno", "Grade 9", "East", ""], ["A2", "Jane", "Otienoo", "Grade 9", "West", ""]]
        self.assertEqual([r["status"] for r in run(rows)["rows"]], ["ready", "ready"])
        paper = run(rows, source="paper")["rows"]
        self.assertEqual([r["status"] for r in paper], ["needs_confirmation", "needs_confirmation"])

    def test_temporary_numbers_continue_after_existing_ones(self):
        existing = [{"admission_number": "NO-ADM-0001", "first_name": "X", "last_name": "Y"}]
        out = run([["", "Jane", "Otieno", "Grade 9", "East", ""]], existing=existing,
                  confirmations={"all": ["missing_admission"]}, provisional_start=1)
        self.assertEqual(out["rows"][0]["admission_number"], "NO-ADM-0002")

    def test_natural_sort_puts_2_before_10(self):
        self.assertLess(natural_key("A-2"), natural_key("A-10"))
