from datetime import date

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from api import connect_guard as g
from api.connect_rules import (
    ADMIN,
    PARENT,
    TEACHER,
    ConnectError,
    check_text,
    display_name,
    ensure_default_channels,
    membership,
    roles_for,
)
from schools.models import (
    AcademicYear,
    ClassLevel,
    ConnectChannel,
    Curriculum,
    Enrollment,
    GuardianProfile,
    School,
    SchoolAdminProfile,
    Stream,
    Student,
    StudentGuardian,
    StaffProfile,
    TeacherProfile,
)


class GuardTests(SimpleTestCase):
    def test_phone_numbers(self):
        for t in ["call 0712345678", "+254 712 345 678 now", "0712-345-678", "(0712) 345 678", "254712345678"]:
            self.assertTrue(g.has_phone(t), t)
        for t in ["meeting on 2026-11-02", "KES 12,500 due", "Form 3 East, room 12", "see you at 10:30", "A1234567890B"]:
            self.assertFalse(g.has_phone(t), t)

    def test_emails(self):
        self.assertTrue(g.has_email("write to a.b@example.com please"))
        self.assertFalse(g.has_email("see you @ 5pm"))

    def test_id_tokens(self):
        self.assertEqual(g.id_tokens("Pay for A1 and 2026/045 by 12 Nov"), ["a1", "2026/045"])
        self.assertEqual(g.id_tokens("Form 3 East"), [])

    def test_names(self):
        self.assertTrue(g.mentions_name(g.name_words("Please help Amani Test today"), "Amani", "Test"))
        self.assertTrue(g.mentions_name(g.name_words("Test Amani is here"), "Amani", "Test"))
        self.assertTrue(g.mentions_name(g.name_words("Amani Test is here"), "Amani James", "Test"))
        self.assertFalse(g.mentions_name(g.name_words("Test results for the class"), "Amani", "Test"))


class RulesTests(TestCase):
    def setUp(self):
        U = get_user_model()
        self.school = School.objects.create(name="Con School", code="con-test")
        self.other = School.objects.create(name="Other Con", code="con-other")
        self.admin = U.objects.create_user("con_admin", "a@example.com", "pw12345!")
        SchoolAdminProfile.objects.create(user=self.admin, school=self.school)
        self.teacher = U.objects.create_user("con_teacher", "t@example.com", "pw12345!")
        TeacherProfile.objects.create(user=self.teacher, school=self.school)
        self.bursar = U.objects.create_user("con_bursar", "b@example.com", "pw12345!")
        StaffProfile.objects.create(user=self.bursar, school=self.school, role="bursar")
        self.secretary = U.objects.create_user("con_secretary", "se@example.com", "pw12345!")
        StaffProfile.objects.create(user=self.secretary, school=self.school, role="secretary")
        self.parent = U.objects.create_user("con_parent", "p@example.com", "pw12345!", first_name="Grace", last_name="Test")
        self.guardian = GuardianProfile.objects.create(user=self.parent, school=self.school, phone="0700000001")
        self.stranger = U.objects.create_user("con_stranger", "s@example.com", "pw12345!")
        self.root = U.objects.create_superuser("con_root", "r@example.com", "pw12345!")
        cur = Curriculum.objects.create(name="Con CBC", code="CCBC")
        g3 = ClassLevel.objects.create(curriculum=cur, name="Grade 3", level_number=3)
        east = Stream.objects.create(school=self.school, class_level=g3, name="East")
        year = AcademicYear.objects.create(
            school=self.school, name="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31)
        )
        self.kid = Student.objects.create(school=self.school, first_name="Amani", last_name="Test", admission_number="A1")
        self.other_kid = Student.objects.create(
            school=self.school, first_name="Baraka", last_name="Mwangi", admission_number="A2"
        )
        self.enr = Enrollment.objects.create(student=self.kid, academic_year=year, class_level=g3, stream=east)
        Enrollment.objects.create(student=self.other_kid, academic_year=year, class_level=g3, stream=east)
        StudentGuardian.objects.create(student=self.kid, guardian=self.guardian)

    def test_roles(self):
        self.assertEqual(membership(self.admin), (self.school.id, ADMIN))
        self.assertEqual(membership(self.teacher), (self.school.id, TEACHER))
        self.assertEqual(membership(self.bursar), (self.school.id, "bursar"))
        self.assertEqual(membership(self.secretary), (self.school.id, "secretary"))
        self.assertEqual(membership(self.parent), (self.school.id, PARENT))
        self.assertEqual(membership(self.stranger), (None, None))
        self.assertEqual(membership(self.root), (None, None))

    def test_parent_needs_a_link_to_an_active_learner(self):
        self.enr.is_active = False
        self.enr.save()
        self.assertEqual(membership(self.parent), (None, None))
        self.enr.is_active = True
        self.enr.save()
        StudentGuardian.objects.all().delete()
        self.assertEqual(membership(self.parent), (None, None))

    def test_default_channels_are_created_once(self):
        ensure_default_channels(self.school.id)
        ensure_default_channels(self.school.id)
        rows = ConnectChannel.objects.filter(school=self.school)
        self.assertEqual(sorted(r.kind for r in rows), ["community", "notices"])
        self.assertTrue(all(r.is_default for r in rows))
        self.assertEqual(ConnectChannel.objects.filter(school=self.other).count(), 0)

    def test_roles_for_and_display_name(self):
        out = roles_for([self.admin.id, self.teacher.id, self.bursar.id, self.secretary.id, self.parent.id])
        self.assertEqual(
            out,
            {
                self.admin.id: ADMIN,
                self.teacher.id: TEACHER,
                self.bursar.id: "bursar",
                self.secretary.id: "secretary",
                self.parent.id: PARENT,
            },
        )
        self.assertEqual(display_name(self.parent, PARENT), "Grace Test")
        self.assertEqual(display_name(self.teacher, TEACHER), "Teacher")
        self.assertNotIn("con_teacher", display_name(self.teacher, TEACHER))

    def test_phone_and_email_blocked_except_for_admin(self):
        for role, user in ((PARENT, self.parent), (TEACHER, self.teacher)):
            with self.assertRaises(ConnectError):
                check_text(self.school.id, role, user, "call me on 0712345678")
            with self.assertRaises(ConnectError):
                check_text(self.school.id, role, user, "write to me@example.com")
        text = "Office line 0712345678"
        self.assertEqual(check_text(self.school.id, ADMIN, self.admin, text), text)

    def test_admission_numbers_blocked_for_everyone(self):
        for role, user in ((ADMIN, self.admin), (TEACHER, self.teacher), (PARENT, self.parent)):
            with self.assertRaises(ConnectError):
                check_text(self.school.id, role, user, "The report for a1 is ready")

    def test_parent_cannot_name_other_learners(self):
        for text in ("Baraka Mwangi is struggling", "mwangi baraka was late", "Amani Test and Baraka Mwangi"):
            with self.assertRaises(ConnectError):
                check_text(self.school.id, PARENT, self.parent, text)
        ok = "My son Amani Test is in Grade 3 East"
        self.assertEqual(check_text(self.school.id, PARENT, self.parent, ok), ok)
        staff = "Well done Baraka Mwangi"
        self.assertEqual(check_text(self.school.id, TEACHER, self.teacher, staff), staff)

    def test_length_and_empty(self):
        with self.assertRaises(ConnectError):
            check_text(self.school.id, ADMIN, self.admin, "   ")
        with self.assertRaises(ConnectError):
            check_text(self.school.id, ADMIN, self.admin, "x" * 2001)
        self.assertEqual(len(check_text(self.school.id, ADMIN, self.admin, "x" * 2000)), 2000)
