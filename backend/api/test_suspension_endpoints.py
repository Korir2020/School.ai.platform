"""A suspended school must be blocked on every protected endpoint in the
calendar, framework, level, national, profile, setup and report views."""
import re

from django.contrib.auth.models import User
from django.urls import URLPattern, URLResolver, get_resolver
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.test import APITestCase

from schools.models import School, SchoolAdminProfile

from .suspension import SchoolNotSuspended

PW = "Xk9-secure-pass"
MODULES = {
    "api.calendar_views",
    "api.framework_views",
    "api.level_views",
    "api.national_views",
    "api.profile_views",
    "api.setup_views",
    "api.report_views",
}
METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")


def _walk(patterns, prefix=""):
    for p in patterns:
        route = prefix + str(p.pattern)
        if isinstance(p, URLResolver):
            yield from _walk(p.url_patterns, route)
        elif isinstance(p, URLPattern):
            yield route, p.callback


def _url(route):
    route = re.sub(r"<(?:\w+:)?\w+>", "1", route)
    if re.search(r"[\^$()\\]", route):
        return None
    return "/" + route


def protected_views():
    found = {}
    for route, callback in _walk(get_resolver().url_patterns):
        cls = getattr(callback, "cls", None)
        if cls is None or cls.__module__ not in MODULES:
            continue
        if AllowAny in cls.permission_classes:
            continue
        info = found.setdefault(cls.__name__, {"cls": cls, "urls": []})
        info["urls"].append(_url(route))
    return found


def endpoints():
    out = []
    for name, info in sorted(protected_views().items()):
        url = next((u for u in info["urls"] if u), None)
        methods = [m for m in METHODS if hasattr(info["cls"], m.lower())]
        out.append((name, url, methods))
    return out


def is_suspension_block(response):
    data = getattr(response, "data", None)
    return (
        response.status_code == 403
        and isinstance(data, dict)
        and "suspended" in str(data.get("detail", "")).lower()
    )


class SuspensionOnProtectedEndpointsTests(APITestCase):
    def setUp(self):
        self.client.raise_request_exception = False
        self.a = School.objects.create(name="A", code="A1")
        self.b = School.objects.create(name="B", code="B1")
        self.boss_a = User.objects.create_user("boss_a", password=PW)
        SchoolAdminProfile.objects.create(user=self.boss_a, school=self.a)
        self.boss_b = User.objects.create_user("boss_b", password=PW)
        SchoolAdminProfile.objects.create(user=self.boss_b, school=self.b)
        self.root = User.objects.create_superuser("root", "r@example.com", PW)

    def suspend(self, school):
        school.is_suspended = True
        school.save()

    def hit(self, user, url, method):
        self.client.force_authenticate(user)
        if method == "GET":
            return self.client.get(url)
        return getattr(self.client, method.lower())(url, {}, format="json")

    def not_blocked(self, user):
        for name, url, methods in endpoints():
            if not url or not methods:
                continue
            method = "GET" if "GET" in methods else methods[0]
            with self.subTest(view=name, method=method):
                r = self.hit(user, url, method)
                self.assertFalse(is_suspension_block(r), "got %s" % r.status_code)

    def test_every_protected_view_declares_the_suspension_rule(self):
        found = protected_views()
        self.assertEqual(len(found), 32, sorted(found))
        for name, info in found.items():
            perms = list(info["cls"].permission_classes)
            with self.subTest(view=name):
                self.assertIn(IsAuthenticated, perms)
                self.assertIn(SchoolNotSuspended, perms)

    def test_every_endpoint_has_a_testable_url(self):
        for name, url, methods in endpoints():
            with self.subTest(view=name):
                self.assertTrue(url, "no plain URL found")
                self.assertTrue(methods, "no HTTP method found")

    def test_suspended_school_is_blocked_on_every_method(self):
        self.suspend(self.a)
        for name, url, methods in endpoints():
            if not url:
                continue
            for method in methods:
                with self.subTest(view=name, method=method):
                    r = self.hit(self.boss_a, url, method)
                    self.assertTrue(is_suspension_block(r), "got %s" % r.status_code)

    def test_active_school_is_not_blocked(self):
        self.not_blocked(self.boss_a)

    def test_other_school_is_not_blocked_when_one_is_suspended(self):
        self.suspend(self.a)
        self.not_blocked(self.boss_b)

    def test_superadmin_is_not_blocked_when_a_school_is_suspended(self):
        self.suspend(self.a)
        self.not_blocked(self.root)

    def test_anonymous_behaviour_is_unchanged(self):
        self.suspend(self.a)
        for name, url, methods in endpoints():
            if not url or not methods:
                continue
            with self.subTest(view=name):
                r = self.hit(None, url, methods[0])
                self.assertIn(r.status_code, (401, 403))
                self.assertFalse(is_suspension_block(r))
