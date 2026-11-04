from django.db import models
from django.test import TestCase
from rest_framework.test import APIClient

from api.test_connect_views import ConnectApiTests as Base
from schools.models import FeedbackEntry

F = "/api/feedback/"


class FeedbackTests(TestCase):
    _user = Base._user
    setUp = Base.setUp

    def client_for(self, user=None):
        c = APIClient()
        if user is not None:
            c.force_authenticate(user)
        return c

    def send(self, who, **body):
        return self.client_for(who).post(F, body, format="json")

    def test_member_rates_and_can_change_but_not_repeat(self):
        r = self.send(self.teacher, kind="rating", rating=3, text="ok")
        self.assertEqual(r.status_code, 201, r.data)
        r = self.send(self.teacher, kind="rating", rating=5)
        self.assertEqual(r.status_code, 200, r.data)
        mine = FeedbackEntry.objects.filter(user=self.teacher, kind="rating")
        self.assertEqual(mine.count(), 1)
        self.assertEqual(mine.first().rating, 5)

    def test_bad_ratings_are_400_not_a_crash(self):
        for bad in ("abc", 0, 6, -1, 4.5, True, None, [], {}, ""):
            r = self.send(self.teacher, kind="rating", rating=bad)
            self.assertEqual(r.status_code, 400, bad)
            self.assertEqual(r.data["error"], "invalid_rating")
        self.assertEqual(FeedbackEntry.objects.count(), 0)

    def test_unknown_kind_is_rejected(self):
        for bad in ("spam", "", None, 5, ["idea"]):
            r = self.send(self.teacher, kind=bad, text="x")
            self.assertEqual(r.status_code, 400, bad)

    def test_text_rules(self):
        self.assertEqual(self.send(self.parent, kind="idea").status_code, 400)
        self.assertEqual(self.send(self.parent, kind="idea", text="   ").status_code, 400)
        self.assertEqual(self.send(self.parent, kind="idea", text="x" * 1001).status_code, 400)
        self.assertEqual(self.send(self.parent, kind="idea", text=["a"]).status_code, 400)
        self.assertEqual(self.send(self.parent, kind="idea", text="x" * 1000).status_code, 201)

    def test_only_connect_members_can_send(self):
        self.assertEqual(self.send(self.stranger, kind="idea", text="hi").status_code, 403)
        r = self.client_for().post(F, {"kind": "idea", "text": "hi"}, format="json")
        self.assertIn(r.status_code, (401, 403))
        self.assertEqual(FeedbackEntry.objects.count(), 0)

    def test_member_sees_only_own_entries(self):
        self.send(self.teacher, kind="idea", text="mine")
        self.send(self.parent, kind="problem", text="theirs")
        r = self.client_for(self.teacher).get(F)
        self.assertEqual(r.status_code, 200)
        self.assertEqual([e["text"] for e in r.data["results"]], ["mine"])

    def test_only_the_superadmin_reads_everything(self):
        self.send(self.teacher, kind="idea", text="hello")
        for who in (self.admin, self.teacher, self.parent, self.other_admin, self.stranger):
            self.assertEqual(self.client_for(who).get(F + "all/").status_code, 403)
            self.assertEqual(self.client_for(who).get(F + "summary/").status_code, 403)
        r = self.client_for(self.root).get(F + "all/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["count"], 1)
        row = r.data["results"][0]
        self.assertEqual(row["school"], "Con School")
        self.assertEqual(row["role"], "Teacher")
        self.assertEqual(row["author"], "Tom Teacher")

    def test_owner_marks_read_and_filters_unread(self):
        self.send(self.teacher, kind="idea", text="hello")
        eid = FeedbackEntry.objects.get().id
        r = self.client_for(self.teacher).post(f"{F}{eid}/read/", {"read": True}, format="json")
        self.assertEqual(r.status_code, 403)
        root = self.client_for(self.root)
        self.assertEqual(root.post(f"{F}{eid}/read/", {"read": True}, format="json").status_code, 200)
        self.assertTrue(FeedbackEntry.objects.get().is_read)
        self.assertEqual(root.get(F + "all/?unread=1").data["count"], 0)
        root.post(f"{F}{eid}/read/", {"read": "false"}, format="json")
        self.assertFalse(FeedbackEntry.objects.get().is_read)
        self.assertEqual(root.post(f"{F}999999/read/", {}, format="json").status_code, 404)

    def test_delete_only_own(self):
        self.send(self.teacher, kind="idea", text="t")
        eid = FeedbackEntry.objects.get().id
        self.assertEqual(self.client_for(self.parent).delete(f"{F}{eid}/").status_code, 404)
        self.assertEqual(FeedbackEntry.objects.count(), 1)
        self.assertEqual(self.client_for(self.teacher).delete(f"{F}{eid}/").status_code, 204)
        self.assertEqual(FeedbackEntry.objects.count(), 0)

    def test_summary_shows_real_numbers_only(self):
        root = self.client_for(self.root)
        r = root.get(F + "summary/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["ratings"], 0)
        self.assertIsNone(r.data["average"])
        self.send(self.teacher, kind="rating", rating=5)
        self.send(self.parent, kind="rating", rating=3)
        self.send(self.other_admin, kind="rating", rating=4)
        self.send(self.admin, kind="idea", text="x")
        r = root.get(F + "summary/")
        self.assertEqual(r.data["ratings"], 3)
        self.assertEqual(r.data["average"], 4.0)
        self.assertEqual(r.data["schools"], 2)
        self.assertEqual(r.data["by_star"], {"1": 0, "2": 0, "3": 1, "4": 1, "5": 1})
        self.assertEqual(r.data["unread"], 4)
        self.assertEqual(r.data["total"], 4)

    def test_pages_and_bad_page_numbers(self):
        FeedbackEntry.objects.bulk_create([
            FeedbackEntry(user=self.teacher, school=self.school, role="teacher", kind="idea", text="n%d" % i)
            for i in range(35)
        ])
        root = self.client_for(self.root)
        r = root.get(F + "all/?page=2")
        self.assertEqual(r.data["count"], 35)
        self.assertEqual(len(r.data["results"]), 5)
        for bad in ("abc", "0", "-3", "99999999999999999999999"):
            r = root.get(F + "all/?page=" + bad)
            self.assertEqual(r.status_code, 200, bad)
            self.assertGreaterEqual(r.data["page"], 1)
        self.assertEqual(root.get(F + "all/?kind=spam").status_code, 400)
        self.assertEqual(root.get(F + "all/?kind=problem").data["count"], 0)

    def test_one_person_cannot_flood(self):
        FeedbackEntry.objects.bulk_create([
            FeedbackEntry(user=self.parent, school=self.school, role="parent", kind="idea", text="n%d" % i)
            for i in range(100)
        ])
        r = self.send(self.parent, kind="idea", text="one more")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["error"], "limit_reached")

    def test_entries_never_block_account_erasure(self):
        user_fk = FeedbackEntry._meta.get_field("user")
        school_fk = FeedbackEntry._meta.get_field("school")
        self.assertIs(user_fk.remote_field.on_delete, models.CASCADE)
        self.assertIs(school_fk.remote_field.on_delete, models.SET_NULL)
