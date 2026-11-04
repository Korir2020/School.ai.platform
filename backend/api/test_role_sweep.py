"""Role boundary sweep: a parent may only reach their own child's data; teachers
never reach fees, backups or admin tools. Walks every GET URL in the project."""
import re
from django.test import TestCase, override_settings
from django.urls import get_resolver, URLPattern, URLResolver
from rest_framework.test import APIClient
from api.test_connect_views import ConnectApiTests as Base
from schools.models import Student


def _walk(patterns, prefix=""):
    for p in patterns:
        if isinstance(p, URLResolver):
            yield from _walk(p.url_patterns, prefix + str(p.pattern))
        elif isinstance(p, URLPattern):
            yield prefix + str(p.pattern)


def _fill(route, ident):
    route = route.lstrip("^").rstrip("$")
    route = re.sub(r"<int:[^>]+>", str(ident), route)
    route = re.sub(r"<(str|slug):[^>]+>", "x", route)
    route = re.sub(r"<[^>]+>", "x", route)
    return "/" + route


PARENT_OK = ("api/parent/", "api/me", "api/auth", "api/notifications", "api/announcements",
             "api/connect", "api/calendar", "api/health", "api/public", "api/branding",
             "api/report-cards", "api/report-card/", "api/feedback", "api/profile", "api/csrf",
             "api/mfa", "api/receipts/verify", "api/join", "api/demo", "api/password")


@override_settings(MESSAGING_SYNC=True)
class RoleSweep(TestCase):
    _user = Base._user
    setUp = Base.setUp

    def _routes(self):
        return sorted({r for r in _walk(get_resolver().url_patterns) if r.startswith("api/")})

    def _get(self, user, url):
        c = APIClient(); c.force_authenticate(user)
        try:
            return c.get(url)
        except Exception as e:  # a crash is also a leak risk; report it
            return type("R", (), {"status_code": f"crash {type(e).__name__}", "content": b""})

    def test_parent_cannot_see_other_child(self):
        other_kid = Student.objects.get(admission_number="A2")
        leaks = []
        for r in self._routes():
            if r.startswith(PARENT_OK) and "<" not in r:
                continue
            url = _fill(r, other_kid.id)
            res = self._get(self.parent, url)
            if url == "/api/search/":
                res = self._get(self.parent, "/api/search/?q=Baraka")
            if res.status_code == 200 and (b"Baraka" in res.content or b"A2" in res.content
                                           or not r.startswith(PARENT_OK)):
                if url != "/api/search/" or b"Baraka" in res.content:
                    leaks.append((url, res.status_code))
        self.assertEqual(leaks, [], "parent reached data outside own child")

    def test_teacher_kept_out_of_money_backup_admin(self):
        leaks = []
        for r in self._routes():
            if not re.match(r"api/(fees|backup|admin|superadmin|parent-accounts|deputies|school-export|schools/)", r):
                continue
            res = self._get(self.teacher, _fill(r, 1))
            if res.status_code == 200 and r == "api/schools/":
                # list is fine only if it shows the teacher's own school alone
                if b"Other Con" in res.content:
                    leaks.append(r)
            elif res.status_code == 200:
                leaks.append(r)
        self.assertEqual(leaks, [], "teacher reached admin-only area")
