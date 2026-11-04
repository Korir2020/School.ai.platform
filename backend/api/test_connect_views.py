from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from api.connect_rules import ensure_default_channels
from schools.models import (
    AcademicYear,
    CalendarEvent,
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
    TeacherProfile,
)

B = "/api/connect/"


class ConnectApiTests(TestCase):
    def _user(self, name, **kw):
        return get_user_model().objects.create_user(name, name + "@example.com", "pw12345!", **kw)

    def setUp(self):
        self.school = School.objects.create(name="Con School", code="con-test")
        self.other = School.objects.create(name="Other Con", code="con-other")
        self.admin = self._user("cv_admin", first_name="Ann", last_name="Admin")
        SchoolAdminProfile.objects.create(user=self.admin, school=self.school)
        self.teacher = self._user("cv_teacher", first_name="Tom", last_name="Teacher")
        TeacherProfile.objects.create(user=self.teacher, school=self.school)
        self.parent = self._user("cv_parent", first_name="Grace", last_name="Test")
        self.parent2 = self._user("cv_parent2", first_name="Peter", last_name="Mwangi")
        g1 = GuardianProfile.objects.create(user=self.parent, school=self.school, phone="0700000001")
        g2 = GuardianProfile.objects.create(user=self.parent2, school=self.school, phone="0700000002")
        self.stranger = self._user("cv_stranger")
        self.root = get_user_model().objects.create_superuser("cv_root", "root@example.com", "pw12345!")
        self.other_admin = self._user("cv_other_admin")
        SchoolAdminProfile.objects.create(user=self.other_admin, school=self.other)
        cur = Curriculum.objects.create(name="Cv CBC", code="CVCBC")
        g3 = ClassLevel.objects.create(curriculum=cur, name="Grade 3", level_number=3)
        east = Stream.objects.create(school=self.school, class_level=g3, name="East")
        year = AcademicYear.objects.create(
            school=self.school, name="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31)
        )
        kid = Student.objects.create(school=self.school, first_name="Amani", last_name="Test", admission_number="A1")
        kid2 = Student.objects.create(school=self.school, first_name="Baraka", last_name="Mwangi", admission_number="A2")
        for s in (kid, kid2):
            Enrollment.objects.create(student=s, academic_year=year, class_level=g3, stream=east)
        StudentGuardian.objects.create(student=kid, guardian=g1)
        StudentGuardian.objects.create(student=kid2, guardian=g2)
        ensure_default_channels(self.school.id)
        self.notices = ConnectChannel.objects.get(school=self.school, kind="notices")
        self.community = ConnectChannel.objects.get(school=self.school, kind="community")

    def _c(self, user=None):
        c = APIClient()
        if user:
            c.force_authenticate(user=user)
        return c

    def say(self, user, channel, body, **extra):
        data = {"body": body}
        data.update(extra)
        return self._c(user).post(f"{B}channels/{channel.id}/posts/", data, format="json")

    def read(self, user, channel, query=""):
        return self._c(user).get(f"{B}channels/{channel.id}/posts/{query}")

    def test_access(self):
        for u in (self.stranger, self.root):
            self.assertEqual(self._c(u).get(B + "channels/").status_code, 403)
        self.assertIn(self._c().get(B + "channels/").status_code, (401, 403))

    def test_channel_list(self):
        r = self._c(self.parent).get(B + "channels/")
        self.assertEqual(r.status_code, 200)
        by = {c["kind"]: c for c in r.data["channels"]}
        self.assertFalse(by["notices"]["can_post"])
        self.assertTrue(by["community"]["can_post"])
        self.assertEqual(r.data["me"]["role"], "parent")
        self.assertFalse(r.data["me"]["is_admin"])
        r = self._c(self.admin).get(B + "channels/")
        by = {c["kind"]: c for c in r.data["channels"]}
        self.assertTrue(by["notices"]["can_post"])
        self.assertTrue(r.data["me"]["is_admin"])

    def test_notices_are_admin_only(self):
        self.assertEqual(self.say(self.parent, self.notices, "Hello").status_code, 403)
        self.assertEqual(self.say(self.teacher, self.notices, "Hello").status_code, 403)
        r = self.say(self.admin, self.notices, "School closes on Friday")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data["author"], "Ann Admin")

    def test_posting_guard_through_the_api(self):
        ok = self.say(self.parent, self.community, "Hello, I am Grace, parent of Amani Test")
        self.assertEqual(ok.status_code, 201)
        for text in ("Call me on 0712345678", "Mail me at g@example.com", "My child A1 is in Grade 3", "Baraka Mwangi was rude"):
            r = self.say(self.parent, self.community, text)
            self.assertEqual(r.status_code, 400, text)
            self.assertEqual(r.data["error"], "post_rejected")
        self.assertEqual(self.say(self.parent, self.community, "   ").status_code, 400)
        self.assertEqual(self.say(self.parent, self.community, 12345).status_code, 400)

    def test_ids_and_counts_are_admin_only(self):
        self.say(self.admin, self.notices, "Term dates are out")
        parent_row = self.read(self.parent, self.notices).data["posts"][0]
        for key in ("author_id", "ack_count", "report_count", "hidden"):
            self.assertNotIn(key, parent_row)
        admin_row = self.read(self.admin, self.notices).data["posts"][0]
        for key in ("author_id", "ack_count", "report_count", "hidden"):
            self.assertIn(key, admin_row)

    def test_only_admin_can_pin_or_mark_urgent(self):
        r = self.say(self.parent, self.community, "Hello all", is_pinned=True, is_urgent=True)
        self.assertEqual(r.status_code, 201)
        self.assertFalse(r.data["is_pinned"])
        self.assertFalse(r.data["is_urgent"])
        r = self.say(self.admin, self.notices, "Fees reminder", is_pinned=True, is_urgent=True)
        self.assertTrue(r.data["is_pinned"])
        self.assertTrue(r.data["is_urgent"])
        self.assertEqual(len(self.read(self.parent, self.notices).data["pinned"]), 1)
        self.assertEqual(self._c(self.parent).patch(f"{B}posts/{r.data['id']}/", {"is_pinned": False}, format="json").status_code, 403)

    def test_pin_limit(self):
        for i in range(3):
            self.assertTrue(self.say(self.admin, self.notices, f"Pinned {i}", is_pinned=True).data["is_pinned"])
        r = self.say(self.admin, self.notices, "One too many", is_pinned=True)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["error"], "too_many_pinned")

    def test_hide_and_delete(self):
        mine = self.say(self.parent, self.community, "Good morning everyone").data["id"]
        self.assertEqual(self._c(self.parent2).delete(f"{B}posts/{mine}/").status_code, 403)
        r = self._c(self.admin).patch(f"{B}posts/{mine}/", {"hidden": True}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data["hidden"])
        self.assertEqual(self.read(self.teacher, self.community).data["posts"], [])
        rows = self.read(self.admin, self.community).data["posts"]
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["hidden"])
        self.assertEqual(self._c(self.parent).delete(f"{B}posts/{mine}/").status_code, 404)
        second = self.say(self.parent, self.community, "Another note").data["id"]
        self.assertEqual(self._c(self.parent).delete(f"{B}posts/{second}/").status_code, 204)
        self.assertEqual(self.read(self.parent, self.community).data["posts"], [])

    def test_acknowledge(self):
        pid = self.say(self.admin, self.notices, "Please read").data["id"]
        for _ in range(2):
            r = self._c(self.parent).post(f"{B}posts/{pid}/ack/")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.data, {"acknowledged": True})
        self._c(self.teacher).post(f"{B}posts/{pid}/ack/")
        self.assertTrue(self.read(self.parent, self.notices).data["posts"][0]["acknowledged"])
        self.assertEqual(self.read(self.admin, self.notices).data["posts"][0]["ack_count"], 2)

    def test_reports(self):
        pid = self.say(self.parent, self.community, "Something unkind").data["id"]
        self.assertEqual(self._c(self.parent).post(f"{B}posts/{pid}/report/", {"reason": "x"}, format="json").status_code, 400)
        r = self._c(self.teacher).post(f"{B}posts/{pid}/report/", {"reason": "Unkind"}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(self._c(self.teacher).post(f"{B}posts/{pid}/report/", {"reason": "Unkind"}, format="json").status_code, 200)
        self.assertEqual(self._c(self.parent2).get(B + "reports/").status_code, 403)
        listing = self._c(self.admin).get(B + "reports/").data["reports"]
        self.assertEqual(len(listing), 1)
        self.assertNotIn("reporter", listing[0])
        self.assertEqual(listing[0]["post"]["body"], "Something unkind")
        self.assertEqual(self.read(self.admin, self.community).data["posts"][0]["report_count"], 1)
        done = self._c(self.admin).post(f"{B}reports/{listing[0]['id']}/resolve/", {"hide": True}, format="json")
        self.assertEqual(done.data, {"resolved": 1})
        self.assertEqual(self._c(self.admin).get(B + "reports/").data["reports"], [])
        self.assertEqual(self.read(self.parent2, self.community).data["posts"], [])

    def test_mute(self):
        url = f"{B}members/{self.parent.id}/mute/"
        self.assertEqual(self._c(self.teacher).post(url).status_code, 403)
        self.assertEqual(self._c(self.admin).post(url).status_code, 201)
        self.assertEqual(self._c(self.admin).post(url).status_code, 200)
        r = self.say(self.parent, self.community, "Hello again")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.data["error"], "muted")
        info = self._c(self.parent).get(B + "channels/").data
        self.assertTrue(info["me"]["muted"])
        self.assertFalse({c["kind"]: c for c in info["channels"]}["community"]["can_post"])
        self.assertEqual(self._c(self.admin).delete(url).status_code, 204)
        self.assertEqual(self.say(self.parent, self.community, "Hello again").status_code, 201)
        self.assertEqual(self._c(self.admin).post(f"{B}members/{self.admin.id}/mute/").status_code, 400)
        self.assertEqual(self._c(self.admin).post(f"{B}members/{self.stranger.id}/mute/").status_code, 404)
        self.assertEqual(self._c(self.other_admin).post(url).status_code, 404)

    def test_schools_are_isolated(self):
        pid = self.say(self.admin, self.notices, "Private to this school").data["id"]
        self.assertEqual(self.read(self.other_admin, self.notices).status_code, 404)
        self.assertEqual(self._c(self.other_admin).patch(f"{B}posts/{pid}/", {"hidden": True}, format="json").status_code, 404)
        self.assertEqual(self._c(self.other_admin).post(f"{B}posts/{pid}/ack/").status_code, 404)
        theirs = self._c(self.other_admin).get(B + "channels/").data["channels"]
        self.assertEqual(len(theirs), 2)
        self.assertNotIn(self.notices.id, [c["id"] for c in theirs])

    def test_unread_counts(self):
        self.say(self.admin, self.notices, "First notice")
        self.say(self.admin, self.notices, "Second notice")

        def unread(user):
            rows = self._c(user).get(B + "channels/").data["channels"]
            return {c["kind"]: c["unread"] for c in rows}["notices"]

        self.assertEqual(unread(self.parent), 2)
        self.assertEqual(unread(self.admin), 0)
        self.read(self.parent, self.notices)
        self.assertEqual(unread(self.parent), 0)

    def test_paging_and_search(self):
        for i in range(1, 6):
            self.say(self.admin, self.notices, f"News item {i}")
        first = self.read(self.parent, self.notices, "?limit=2").data
        self.assertEqual([p["body"] for p in first["posts"]], ["News item 5", "News item 4"])
        self.assertTrue(first["has_more"])
        nxt = self.read(self.parent, self.notices, f"?limit=2&before={first['posts'][-1]['id']}").data
        self.assertEqual([p["body"] for p in nxt["posts"]], ["News item 3", "News item 2"])
        last = self.read(self.parent, self.notices, f"?limit=2&before={nxt['posts'][-1]['id']}").data
        self.assertEqual([p["body"] for p in last["posts"]], ["News item 1"])
        self.assertFalse(last["has_more"])
        found = self.read(self.parent, self.notices, "?q=item 3").data["posts"]
        self.assertEqual([p["body"] for p in found], ["News item 3"])

    def test_attach_calendar_event(self):
        mine = CalendarEvent.objects.create(school=self.school, title="Open Day", start_date=date(2026, 12, 1))
        theirs = CalendarEvent.objects.create(school=self.other, title="Other Day", start_date=date(2026, 12, 2))
        r = self.say(self.admin, self.notices, "Join us", event_id=mine.id)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data["event"]["title"], "Open Day")
        self.assertEqual(self.say(self.admin, self.notices, "Join us", event_id=theirs.id).status_code, 404)
        self.assertEqual(self.say(self.parent, self.community, "Hello", event_id=mine.id).status_code, 403)

    def test_member_list_hides_parents_from_parents(self):
        r = self._c(self.parent).get(B + "members/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["parent_count"], 2)
        self.assertEqual([m["name"] for m in r.data["members"]], ["Ann Admin", "Tom Teacher"])
        for m in r.data["members"]:
            self.assertNotIn("user_id", m)
        self._c(self.admin).post(f"{B}members/{self.parent.id}/mute/")
        rows = self._c(self.admin).get(B + "members/").data["members"]
        by = {m["name"]: m for m in rows}
        self.assertEqual(set(by), {"Ann Admin", "Tom Teacher", "Grace Test", "Peter Mwangi"})
        self.assertTrue(by["Grace Test"]["muted"])
        self.assertFalse(by["Peter Mwangi"]["muted"])
        found = self._c(self.admin).get(B + "members/?q=peter").data["members"]
        self.assertEqual(sorted(m["name"] for m in found), ["Ann Admin", "Peter Mwangi", "Tom Teacher"])

    def test_delete_is_permanent(self):
        from schools.models import ConnectAck, ConnectPost
        mine = self.say(self.parent, self.community, "Delete me").data["id"]
        ConnectAck.objects.create(post_id=mine, user=self.admin)
        self.assertEqual(self._c(self.parent2).delete(f"{B}posts/{mine}/").status_code, 403)
        self.assertTrue(ConnectPost.objects.filter(pk=mine).exists())
        self.assertEqual(self._c(self.parent).delete(f"{B}posts/{mine}/").status_code, 204)
        self.assertFalse(ConnectPost.objects.filter(pk=mine).exists())
        self.assertFalse(ConnectAck.objects.filter(post_id=mine).exists())
        self.assertEqual(self.read(self.admin, self.community).data["posts"], [])
        self.assertEqual(self._c(self.parent).delete(f"{B}posts/{mine}/").status_code, 404)

    def test_admin_can_delete_any_post_permanently(self):
        from schools.models import ConnectPost
        pid = self.say(self.parent, self.community, "Hello").data["id"]
        self.assertEqual(self._c(self.admin).delete(f"{B}posts/{pid}/").status_code, 204)
        self.assertFalse(ConnectPost.objects.filter(pk=pid).exists())
        self.assertEqual(self._c(self.admin).delete(f"{B}posts/{pid}/").status_code, 404)

    def test_other_school_admin_cannot_delete(self):
        from schools.models import ConnectPost
        pid = self.say(self.parent, self.community, "Private").data["id"]
        r = self._c(self.other_admin).delete(f"{B}posts/{pid}/")
        self.assertIn(r.status_code, (403, 404))
        self.assertTrue(ConnectPost.objects.filter(pk=pid).exists())

    def test_anonymous_cannot_delete(self):
        from schools.models import ConnectPost
        pid = self.say(self.parent, self.community, "Public eyes").data["id"]
        r = self._c().delete(f"{B}posts/{pid}/")
        self.assertIn(r.status_code, (401, 403))
        self.assertTrue(ConnectPost.objects.filter(pk=pid).exists())
