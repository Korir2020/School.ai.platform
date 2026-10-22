from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase

from api.level_rules import (
    DEFAULT_LEVELS, LevelError, create_scale, move, roster, save_level, scale_for,
)
from schools.models import (
    AcademicYear, ClassLevel, Curriculum, Enrollment, LevelResult, MarkAuditLog, School,
    SchoolAdminProfile, Stream, Student, Subject, TeacherAssignment, TeacherProfile, Term,
)


class LevelRulesTests(TestCase):
    def setUp(self):
        U = get_user_model()
        self.school = School.objects.create(name="Lvl School", code="lvl-test")
        self.other = School.objects.create(name="Other School", code="lvl-other")
        self.admin = U.objects.create_user("lv_admin", "a@example.com", "pw12345!")
        SchoolAdminProfile.objects.create(user=self.admin, school=self.school)
        self.teacher = U.objects.create_user("lv_teacher", "t@example.com", "pw12345!")
        self.tprof = TeacherProfile.objects.create(user=self.teacher, school=self.school)
        self.stranger = U.objects.create_user("lv_other", "o@example.com", "pw12345!")
        TeacherProfile.objects.create(user=self.stranger, school=self.school)
        self.cur = Curriculum.objects.create(name="Lvl CBC", code="LCBC")
        self.g3 = ClassLevel.objects.create(curriculum=self.cur, name="Grade 3", level_number=3)
        self.g8 = ClassLevel.objects.create(curriculum=self.cur, name="Grade 8", level_number=8)
        self.east = Stream.objects.create(school=self.school, class_level=self.g3, name="East")
        self.west = Stream.objects.create(school=self.school, class_level=self.g3, name="West")
        self.year = AcademicYear.objects.create(
            school=self.school, name="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        self.term = Term.objects.create(
            academic_year=self.year, name="Term 1", start_date=date(2026, 1, 1), end_date=date(2026, 4, 30))
        self.math = Subject.objects.create(school=self.school, name="Mathematics")
        self.art = Subject.objects.create(school=self.school, name="Art")
        TeacherAssignment.objects.create(
            teacher=self.tprof, school=self.school, subject=self.math, stream=self.east)
        self.kid = Student.objects.create(
            school=self.school, first_name="Amani", last_name="Test", admission_number="A1")
        Enrollment.objects.create(
            student=self.kid, academic_year=self.year, class_level=self.g3, stream=self.east)
        self.scale = create_scale(self.school, self.cur, 1, 6, self.admin)

    def _save(self, user=None, level="meets", subject=None):
        return save_level(user or self.teacher, self.kid, subject or self.math,
                          self.year, self.term, "end", level, "Good effort")

    def test_default_scale_is_school_set_and_editable(self):
        self.assertEqual(self.scale.source, "school")
        self.assertEqual(self.scale.keys(), [x["key"] for x in DEFAULT_LEVELS])

    def test_scale_covers_only_its_levels(self):
        self.assertEqual(scale_for(self.school.id, self.g3), self.scale)
        self.assertIsNone(scale_for(self.school.id, self.g8))

    def test_only_admin_creates_scale(self):
        with self.assertRaises(LevelError):
            create_scale(self.school, self.cur, 1, 6, self.teacher)

    def test_bad_levels_refused(self):
        with self.assertRaises(LevelError):
            create_scale(self.school, self.cur, 1, 6, self.admin, levels=[{"key": "a", "label": "A"}])
        dup = [{"key": "a", "label": "A"}, {"key": "a", "label": "B"}]
        with self.assertRaises(LevelError):
            create_scale(self.school, self.cur, 1, 6, self.admin, levels=dup)

    def test_new_scale_version_increases(self):
        v2 = create_scale(self.school, self.cur, 1, 6, self.admin)
        self.assertEqual(v2.version, 2)

    def test_assigned_teacher_saves_and_it_is_audited(self):
        r = self._save()
        self.assertEqual((r.level_key, r.status), ("meets", "draft"))
        log = MarkAuditLog.objects.get(action="level_save")
        self.assertIsNone(log.performance)

    def test_unassigned_teacher_and_wrong_subject_refused(self):
        with self.assertRaises(LevelError):
            self._save(user=self.stranger)
        with self.assertRaises(LevelError):
            self._save(subject=self.art)

    def test_free_text_level_refused(self):
        with self.assertRaises(LevelError):
            self._save(level="brilliant")

    def test_no_scale_for_class_refused(self):
        kid8 = Student.objects.create(
            school=self.school, first_name="B", last_name="C", admission_number="B8")
        s8 = Stream.objects.create(school=self.school, class_level=self.g8, name="N")
        Enrollment.objects.create(student=kid8, academic_year=self.year, class_level=self.g8, stream=s8)
        TeacherAssignment.objects.create(
            teacher=self.tprof, school=self.school, subject=self.math, stream=s8)
        with self.assertRaises(LevelError):
            save_level(self.teacher, kid8, self.math, self.year, self.term, "end", "meets")

    def test_full_flow_and_locks(self):
        r = self._save()
        move(self.teacher, r, "submit")
        with self.assertRaises(LevelError):
            move(self.teacher, r, "approve")
        move(self.admin, r, "approve")
        with self.assertRaises(LevelError):
            self._save(level="exceeds")
        move(self.admin, r, "lock")
        self.assertEqual(LevelResult.objects.get(pk=r.pk).status, "locked")

    def test_reject_returns_to_draft_and_allows_edit(self):
        r = self._save()
        move(self.teacher, r, "submit")
        move(self.admin, r, "reject")
        self.assertEqual(self._save(level="exceeds").level_key, "exceeds")

    def test_roster_shows_level_and_blocks_others(self):
        self._save()
        data = roster(self.teacher, self.math, self.east, self.year, self.term, "end")
        self.assertEqual(data["rows"][0]["level"], "meets")
        self.assertEqual(len(data["levels"]), 4)
        with self.assertRaises(LevelError):
            roster(self.teacher, self.math, self.west, self.year, self.term, "end")
