from unittest import mock

from django.contrib.auth.models import User
from django.core.cache import cache
from rest_framework.test import APITestCase

from api.auth_throttle import LoginRateThrottle

LOGIN = "/api/auth/login/"


class LoginThrottleTests(APITestCase):
    def setUp(self):
        cache.clear()
        User.objects.create_user("u", password="pass12345")

    def tearDown(self):
        cache.clear()

    def post(self, password):
        body = {"username": "u", "password": password}
        return self.client.post(LOGIN, body).status_code

    def test_repeated_attempts_are_blocked(self):
        rates = {"login": "3/min"}
        with mock.patch.object(LoginRateThrottle, "THROTTLE_RATES", rates):
            codes = [self.post("wrong") for _ in range(5)]
        self.assertEqual(codes, [401, 401, 401, 429, 429])

    def test_normal_login_still_works(self):
        self.assertEqual(self.post("pass12345"), 200)
