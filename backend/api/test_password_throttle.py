from unittest import mock

from django.contrib.auth.models import User
from django.core.cache import cache
from rest_framework.test import APITestCase

from api.password_throttle import PasswordRateThrottle

URL = "/api/auth/change-password/"
NEWPW = "Str0ng-pass-91"


class PasswordThrottleTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.u = User.objects.create_user("pu", password="pass12345")
        self.client.force_authenticate(self.u)

    def tearDown(self):
        cache.clear()

    def post(self, old):
        body = {"old_password": old, "new_password": NEWPW}
        return self.client.post(URL, body, format="json").status_code

    def test_repeated_guesses_are_blocked(self):
        rates = {"password": "3/min"}
        with mock.patch.object(PasswordRateThrottle, "THROTTLE_RATES", rates):
            codes = [self.post("wrong") for _ in range(5)]
        self.assertEqual(codes, [400, 400, 400, 429, 429])

    def test_normal_change_still_works(self):
        self.assertEqual(self.post("pass12345"), 200)
        self.u.refresh_from_db()
        self.assertTrue(self.u.check_password(NEWPW))

    def test_anonymous_still_gets_401(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.post("pass12345"), 401)
