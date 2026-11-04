from django.contrib.auth.models import User
from django.core import mail
from django.test import override_settings
from rest_framework.test import APITestCase

from schools.models import DemoRequest

LOGIN, REFRESH = "/api/auth/login/", "/api/auth/refresh/"
DEMO = "/api/demo-requests/"
GOOD = {"full_name": "Jane Wanjiru", "email": "jane@school.ac.ke", "phone": "+254 700 000000",
        "school_name": "Hill Academy", "role": "headteacher", "learners": 450, "county": "Nakuru"}


class EmailLoginTests(APITestCase):
    def setUp(self):
        User.objects.create_user("tom", email="Tom@School.ac.ke", password="pass-12345")

    def test_username_login(self):
        self.assertEqual(self.client.post(LOGIN, {"username": "tom", "password": "pass-12345"}).status_code, 200)

    def test_email_login_case_insensitive(self):
        r = self.client.post(LOGIN, {"username": "tom@school.ac.ke", "password": "pass-12345"})
        self.assertEqual(r.status_code, 200)

    def test_shared_email_is_refused(self):
        User.objects.create_user("tom2", email="tom@school.ac.ke", password="pass-12345")
        r = self.client.post(LOGIN, {"username": "tom@school.ac.ke", "password": "pass-12345"})
        self.assertEqual(r.status_code, 401)

    def test_email_wrong_password(self):
        r = self.client.post(LOGIN, {"username": "tom@school.ac.ke", "password": "nope-12345"})
        self.assertEqual(r.status_code, 401)


class RememberMeTests(APITestCase):
    def setUp(self):
        User.objects.create_user("ann", password="pass-12345")

    def test_remember_on_keeps_seven_days(self):
        r = self.client.post(LOGIN, {"username": "ann", "password": "pass-12345", "remember": True}, format="json")
        self.assertEqual(r.cookies["marian_rt"]["max-age"], 7 * 24 * 3600)

    def test_remember_off_is_browser_session_and_survives_refresh(self):
        r = self.client.post(LOGIN, {"username": "ann", "password": "pass-12345", "remember": False}, format="json")
        self.assertEqual(r.cookies["marian_rt"]["max-age"], "")
        self.assertEqual(r.cookies["marian_rm"].value, "0")
        r2 = self.client.post(REFRESH, {}, format="json")
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.cookies["marian_rt"]["max-age"], "")


class DemoRequestTests(APITestCase):
    def test_valid_request_is_saved(self):
        r = self.client.post(DEMO, GOOD, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(DemoRequest.objects.get().school_name, "Hill Academy")

    def test_bad_email_rejected(self):
        r = self.client.post(DEMO, {**GOOD, "email": "nope"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("email", r.json())

    def test_missing_school_rejected(self):
        r = self.client.post(DEMO, {**GOOD, "school_name": " "}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_unknown_role_rejected(self):
        self.assertEqual(self.client.post(DEMO, {**GOOD, "role": "superadmin"}, format="json").status_code, 400)

    def test_honeypot_not_saved(self):
        r = self.client.post(DEMO, {**GOOD, "website": "spam.example"}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(DemoRequest.objects.count(), 0)

    @override_settings(DEMO_REQUEST_NOTIFY="team@marian.test",
                       EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_team_notified(self):
        self.client.post(DEMO, GOOD, format="json")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Hill Academy", mail.outbox[0].subject)


class SuperadminTwoStepLoginTests(APITestCase):
    def setUp(self):
        import time
        from django.contrib.auth.hashers import make_password
        from schools.models import SuperadminSecurity
        from api.totp import code_for, new_secret
        self.boss = User.objects.create_superuser("boss", password="pass-12345")
        self.secret = new_secret()
        SuperadminSecurity.objects.create(user=self.boss, totp_secret=self.secret, mfa_enabled=True,
                                          recovery_code_hashes=[make_password("recover-1")])
        self.code = code_for(self.secret, int(time.time()) // 30)
        User.objects.create_superuser("boss2", password="pass-12345")  # no MFA enrolled

    def go(self, **extra):
        return self.client.post(LOGIN, {"username": "boss", "password": "pass-12345", **extra}, format="json")

    def test_password_alone_is_not_enough(self):
        r = self.go()
        self.assertEqual(r.status_code, 401)
        self.assertTrue(r.data["mfa_required"])
        self.assertNotIn("access", r.data)
        self.assertNotIn("marian_rt", r.cookies)

    def test_wrong_code_refused(self):
        self.assertEqual(self.go(mfa_code="000000" if self.code != "000000" else "111111").status_code, 401)

    def test_correct_code_signs_in(self):
        r = self.go(mfa_code=self.code)
        self.assertEqual(r.status_code, 200)
        self.assertIn("access", r.data)

    def test_recovery_code_works_once(self):
        self.assertEqual(self.go(mfa_code="recover-1").status_code, 200)
        self.assertEqual(self.go(mfa_code="recover-1").status_code, 401)

    def test_wrong_password_never_reveals_mfa(self):
        r = self.client.post(LOGIN, {"username": "boss", "password": "bad-12345"}, format="json")
        self.assertEqual(r.status_code, 401)
        self.assertNotIn("mfa_required", r.data)

    def test_superadmin_without_mfa_and_normal_users_unchanged(self):
        r = self.client.post(LOGIN, {"username": "boss2", "password": "pass-12345"}, format="json")
        self.assertEqual(r.status_code, 200)
