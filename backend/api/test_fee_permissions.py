from django.contrib.auth.models import AnonymousUser, User
from django.test import TestCase
from rest_framework.exceptions import PermissionDenied

from api.fee_permissions import get_fee_access_school_id
from schools.models import School, SchoolAdminProfile, StaffProfile, TeacherProfile


class FeeAccessPermissionTests(TestCase):
    denied_detail = "You do not have permission to access fee information."

    def setUp(self):
        self.school = School.objects.create(name="Fee School", code="FEE1")
        self.other_school = School.objects.create(name="Other School", code="FEE2")

    def make_user(self, username):
        return User.objects.create_user(username, password="pass12345")

    def assert_denied(self, user, school_id=None):
        with self.assertRaises(PermissionDenied) as raised:
            get_fee_access_school_id(user, school_id=school_id)
        self.assertEqual(str(raised.exception.detail), self.denied_detail)

    def test_non_deputy_school_administrator_is_allowed_and_scoped(self):
        user = self.make_user("fee_admin")
        SchoolAdminProfile.objects.create(user=user, school=self.school, is_deputy=False)

        self.assertEqual(get_fee_access_school_id(user), self.school.id)
        self.assertEqual(get_fee_access_school_id(user, self.school.id), self.school.id)

    def test_same_school_bursar_is_allowed_and_scoped(self):
        user = self.make_user("fee_bursar")
        StaffProfile.objects.create(user=user, school=self.school, role="bursar")

        self.assertEqual(get_fee_access_school_id(user), self.school.id)
        self.assertEqual(get_fee_access_school_id(user, str(self.school.id)), self.school.id)

    def test_deputy_is_denied(self):
        user = self.make_user("fee_deputy")
        SchoolAdminProfile.objects.create(user=user, school=self.school, is_deputy=True)
        self.assert_denied(user)

    def test_superuser_is_denied_even_with_non_deputy_school_profile(self):
        user = User.objects.create_superuser("fee_root", "root@example.test", "pass12345")
        SchoolAdminProfile.objects.create(user=user, school=self.school, is_deputy=False)
        self.assert_denied(user)
        self.assert_denied(user, self.school.id)

    def test_teacher_secretary_other_staff_and_unprofiled_users_are_denied(self):
        teacher = self.make_user("fee_teacher")
        TeacherProfile.objects.create(user=teacher, school=self.school)
        secretary = self.make_user("fee_secretary")
        StaffProfile.objects.create(user=secretary, school=self.school, role="secretary")
        other_staff = self.make_user("fee_other_staff")
        StaffProfile.objects.create(user=other_staff, school=self.school, role="other")
        unprofiled = self.make_user("fee_unprofiled")

        for user in (teacher, secretary, other_staff, unprofiled):
            with self.subTest(user=user.username):
                self.assert_denied(user)
                self.assert_denied(user, self.school.id)

    def test_anonymous_user_is_denied_with_generic_detail(self):
        self.assert_denied(AnonymousUser())
        self.assert_denied(AnonymousUser(), self.school.id)

    def test_admin_and_bursar_from_another_school_cannot_access_target_school(self):
        admin = self.make_user("fee_other_admin")
        SchoolAdminProfile.objects.create(
            user=admin, school=self.other_school, is_deputy=False
        )
        bursar = self.make_user("fee_other_bursar")
        StaffProfile.objects.create(user=bursar, school=self.other_school, role="bursar")

        for user in (admin, bursar):
            with self.subTest(user=user.username):
                self.assertEqual(get_fee_access_school_id(user), self.other_school.id)
                self.assert_denied(user, self.school.id)

    def test_ambiguous_eligible_profiles_fail_closed_without_target(self):
        user = self.make_user("fee_multi_role")
        SchoolAdminProfile.objects.create(user=user, school=self.school, is_deputy=False)
        StaffProfile.objects.create(user=user, school=self.other_school, role="bursar")

        self.assert_denied(user)
        self.assertEqual(get_fee_access_school_id(user, self.school.id), self.school.id)
        self.assertEqual(
            get_fee_access_school_id(user, self.other_school.id), self.other_school.id
        )
