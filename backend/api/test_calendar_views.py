from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from schools.models import (
    AcademicYear,
    CalendarEvent,
    School,
    SchoolAdminProfile,
    TeacherProfile,
    Term,
)

URL = "/api/calendar/events/"
MARCH = "?from=2026-03-01&to=2026-03-31"


class CalendarApiTests(TestCase):
    def setUp(self):
        U = get_user_model()
        self.school = School.objects.create(name="Cal School", code="cal-test")
        self.other = School.objects.create(name="Other Cal", code="cal-other")
        self.admin = U.objects.create_user("cal_admin", "a@example.com", "pw12345!")
        SchoolAdminProfile.objects.create(user=self.admin, school=self.school)
        self.teacher = U.objects.create_user("cal_teacher", "t@example.com", "pw12345!")
        TeacherProfile.objects.create(user=self.teacher, school=self.school)
        self.outsider = U.objects.create_user("cal_out", "o@example.com", "pw12345!")
        SchoolAdminProfile.objects.create(user=self.outsider, school=self.other)
        self.nobody = U.objects.create_user("cal_nobody", "n@example.com", "pw12345!")
        self.year = AcademicYear.objects.create(
            school=self.school, name="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31)
        )
        self.term = Term.objects.create(
            academic_year=self.year, name="Term 1", start_date=date(2026, 1, 5), end_date=date(2026, 4, 3)
        )

    def _c(self, user=None):
        c = APIClient()
        if user:
            c.force_authenticate(user=user)
        return c

    def _post(self, user, **over):
        body = {"title": "Sports Day", "kind": "event", "start_date": "2026-03-10"}
        body.update(over)
        return self._c(user).post(URL, body, format="json")

    def _make(self, title, start, end=None, school=None):
        return CalendarEvent.objects.create(
            school=school or self.school, title=title, start_date=start, end_date=end
        )

    def test_admin_creates_event(self):
        r = self._post(self.admin)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data["title"], "Sports Day")
        row = CalendarEvent.objects.get()
        self.assertEqual(row.school, self.school)
        self.assertEqual(row.created_by, self.admin)

    def test_blank_end_date_is_allowed(self):
        r = self._post(self.admin, end_date="")
        self.assertEqual(r.status_code, 201)
        self.assertIsNone(r.data["end_date"])

    def test_teacher_reads_but_cannot_write(self):
        self.assertEqual(self._post(self.teacher).status_code, 403)
        self._post(self.admin)
        r = self._c(self.teacher).get(URL + MARCH)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data["events"]), 1)
        self.assertFalse(r.data["can_edit"])
        r = self._c(self.admin).get(URL + MARCH)
        self.assertTrue(r.data["can_edit"])

    def test_user_without_school_is_blocked(self):
        self.assertEqual(self._c(self.nobody).get(URL + MARCH).status_code, 403)

    def test_anonymous_is_blocked(self):
        self.assertIn(self._c().get(URL + MARCH).status_code, (401, 403))

    def test_other_school_cannot_see_or_change_events(self):
        self._post(self.admin)
        eid = CalendarEvent.objects.get().id
        r = self._c(self.outsider).get(URL + MARCH)
        self.assertEqual(r.data["events"], [])
        self.assertEqual(r.data["terms"], [])
        detail = URL + str(eid) + "/"
        self.assertEqual(self._c(self.outsider).patch(detail, {"title": "x"}, format="json").status_code, 404)
        self.assertEqual(self._c(self.outsider).delete(detail).status_code, 404)
        self.assertEqual(CalendarEvent.objects.get().title, "Sports Day")

    def test_range_returns_overlapping_events_only(self):
        self._make("single", date(2026, 3, 10))
        self._make("starts before", date(2026, 2, 25), date(2026, 3, 2))
        self._make("ends after", date(2026, 3, 30), date(2026, 4, 2))
        self._make("after", date(2026, 4, 10))
        self._make("before", date(2026, 2, 1), date(2026, 2, 5))
        self._make("foreign", date(2026, 3, 10), school=self.other)
        r = self._c(self.admin).get(URL + MARCH)
        self.assertEqual(
            sorted(e["title"] for e in r.data["events"]),
            ["ends after", "single", "starts before"],
        )

    def test_terms_come_with_the_range(self):
        r = self._c(self.admin).get(URL + MARCH)
        self.assertEqual([t["name"] for t in r.data["terms"]], ["Term 1"])
        r = self._c(self.admin).get(URL + "?from=2026-06-01&to=2026-06-30")
        self.assertEqual(r.data["terms"], [])

    def test_event_validation(self):
        cases = [
            {"end_date": "2026-03-01"},
            {"kind": "party"},
            {"title": "   "},
            {"start_date": "2026-02-30"},
            {"start_date": "soon"},
            {"end_date": "2027-12-01"},
            {"title": "x" * 121},
        ]
        for over in cases:
            with self.subTest(over=over):
                self.assertEqual(self._post(self.admin, **over).status_code, 400)
        self.assertEqual(CalendarEvent.objects.count(), 0)

    def test_range_validation(self):
        for q in ("", "?from=2026-03-01", "?from=2026-03-31&to=2026-03-01", "?from=2026-01-01&to=2027-12-31"):
            with self.subTest(q=q):
                self.assertEqual(self._c(self.admin).get(URL + q).status_code, 400)

    def test_update_and_delete(self):
        self._post(self.admin)
        eid = CalendarEvent.objects.get().id
        detail = URL + str(eid) + "/"
        r = self._c(self.admin).patch(detail, {"title": "Cross Country"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["title"], "Cross Country")
        self.assertEqual(r.data["kind"], "event")
        r = self._c(self.admin).patch(detail, {"end_date": "2026-03-01"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIsNone(CalendarEvent.objects.get().end_date)
        self.assertEqual(self._c(self.teacher).patch(detail, {"title": "x"}, format="json").status_code, 403)
        self.assertEqual(self._c(self.teacher).delete(detail).status_code, 403)
        self.assertEqual(self._c(self.admin).delete(detail).status_code, 204)
        self.assertEqual(CalendarEvent.objects.count(), 0)
