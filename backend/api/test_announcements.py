import os
from unittest import mock

from django.core import mail
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from api.test_connect_views import ConnectApiTests as Base
from schools.models import (
    Announcement, AnnouncementRecipient, MarkAuditLog, Notification, NotificationPreference,
    StaffProfile, Stream, TeacherProfile,
)

URL = "/api/announcements/"
SMS_ON = {"DJANGO_SMS_PROVIDER": "console"}


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", MESSAGING_SYNC=True)
class AnnouncementTests(TestCase):
    _user = Base._user
    setUp_base = Base.setUp

    def setUp(self):
        self.setUp_base()
        for u, e in ((self.admin, "admin@x.ke"), (self.teacher, "t@x.ke"), (self.parent, "p1@x.ke"), (self.parent2, "")):
            u.email = e
            u.save()
        TeacherProfile.objects.filter(user=self.teacher).update(phone="0711000111")
        self.bursar = self._user("cv_bursar")
        StaffProfile.objects.create(user=self.bursar, school=self.school, role="bursar")

    def c(self, user):
        c = APIClient()
        c.force_authenticate(user)
        return c

    def send(self, user=None, **extra):
        data = {"title": "Closing day", "body": "School closes on Friday at noon.", "audience": "everyone"}
        data.update(extra)
        return self.c(user or self.admin).post(URL, data, format="json")

    def test_only_admins_can_send(self):
        for u in (self.teacher, self.parent, self.bursar):
            self.assertEqual(self.send(u).status_code, 403)
        self.assertEqual(APIClient().post(URL, {}, format="json").status_code, 401)

    def test_everyone_gets_in_app_alert_and_feed_item(self):
        r = self.send()
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["total"], 5)  # admin, teacher, bursar, two parents
        for u in (self.teacher, self.parent, self.parent2, self.bursar):
            self.assertTrue(Notification.objects.filter(recipient=u, kind="announcement").exists())
            feed = self.c(u).get(URL).data
            self.assertEqual(feed["unread"], 1)
            self.assertEqual(feed["results"][0]["title"], "Closing day")
        self.assertFalse(Notification.objects.filter(recipient=self.admin, kind="announcement").exists())
        self.assertTrue(MarkAuditLog.objects.filter(action="announcement_sent").exists())

    def test_other_school_sees_nothing(self):
        a = self.send().data["id"]
        self.assertEqual(self.c(self.other_admin).get(URL).data["results"], [])
        self.assertEqual(self.c(self.other_admin).get(f"{URL}{a}/").status_code, 404)
        self.assertEqual(self.c(self.stranger).get(f"{URL}{a}/").status_code, 404)

    def test_email_uses_bcc_and_respects_opt_out(self):
        NotificationPreference.objects.create(user=self.parent, email_alerts=False)
        r = self.send(send_email=True)
        self.assertEqual(len(mail.outbox), 1)
        m = mail.outbox[0]
        self.assertEqual(sorted(m.bcc), ["admin@x.ke", "cv_bursar@example.com", "t@x.ke"])
        self.assertIn("Closing day", m.subject)
        self.assertIn("Alert settings", m.body)
        rows = {x.user_id: x.email_status for x in AnnouncementRecipient.objects.filter(announcement_id=r.data["id"])}
        self.assertEqual(rows[self.parent.id], "opted_out")
        self.assertEqual(rows[self.parent2.id], "no_contact")
        self.assertEqual(rows[self.teacher.id], "sent")
        self.assertEqual(Announcement.objects.get(pk=r.data["id"]).status, "sent")

    @mock.patch.dict(os.environ, SMS_ON)
    def test_sms_goes_to_valid_phones_only(self):
        r = self.send(send_sms=True, audience="parents")
        rows = {x.user_id: x for x in AnnouncementRecipient.objects.filter(announcement_id=r.data["id"])}
        self.assertEqual(rows[self.parent.id].sms_status, "sent")
        self.assertEqual(rows[self.parent.id].sms_phone, "+254700000001")
        self.assertEqual(r.data["total"], 2)

    @mock.patch.dict(os.environ, {"DJANGO_SMS_PROVIDER": ""})
    def test_sms_without_provider_is_reported_not_faked(self):
        r = self.send(send_sms=True, audience="parents")
        statuses = set(AnnouncementRecipient.objects.filter(announcement_id=r.data["id"]).values_list("sms_status", flat=True))
        self.assertEqual(statuses, {"not_configured"})
        self.assertEqual(Announcement.objects.get(pk=r.data["id"]).status, "partial")

    @mock.patch.dict(os.environ, {**SMS_ON, "DJANGO_SMS_MAX_PER_ANNOUNCEMENT": "1"})
    def test_sms_limit_per_announcement(self):
        r = self.send(send_sms=True, audience="parents")
        statuses = sorted(AnnouncementRecipient.objects.filter(announcement_id=r.data["id"]).values_list("sms_status", flat=True))
        self.assertEqual(statuses, ["over_limit", "sent"])

    def test_class_scope_only_for_parents_and_own_school(self):
        east = Stream.objects.get(school=self.school, name="East")
        self.assertEqual(self.send(audience="teachers", stream=east.id).status_code, 400)
        foreign = Stream.objects.create(school=self.other, class_level=east.class_level, name="West")
        self.assertEqual(self.send(audience="parents", stream=foreign.id).status_code, 400)
        r = self.send(audience="parents", stream=east.id)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data["total"], 2)
        self.assertEqual(r.data["audience_label"], f"Parents of {east}")

    def test_preview_counts_without_sending(self):
        r = self.c(self.admin).post(URL + "preview/", {"audience": "parents", "send_email": True}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["recipients"], 2)
        self.assertEqual(r.data["email"]["will_send"], 1)
        self.assertEqual(r.data["email"]["no_email"], 1)
        self.assertFalse(Announcement.objects.exists())

    def test_draft_edit_send_then_locked(self):
        a = self.send(draft=True).data
        self.assertEqual(a["status"], "draft")
        self.assertFalse(Notification.objects.filter(kind="announcement").exists())
        p = self.c(self.admin).patch(f"{URL}{a['id']}/", {"title": "Closing day moved"}, format="json")
        self.assertEqual(p.data["title"], "Closing day moved")
        s = self.c(self.admin).post(f"{URL}{a['id']}/send/")
        self.assertEqual(s.status_code, 200)
        self.assertEqual(self.c(self.admin).post(f"{URL}{a['id']}/send/").status_code, 409)
        self.assertEqual(self.c(self.admin).patch(f"{URL}{a['id']}/", {"title": "x y z"}, format="json").status_code, 409)

    def test_read_marks_only_own_row(self):
        a = self.send().data["id"]
        self.assertEqual(self.c(self.parent).post(f"{URL}{a}/read/").status_code, 200)
        self.assertEqual(self.c(self.parent).get(URL).data["unread"], 0)
        self.assertEqual(self.c(self.parent2).get(URL).data["unread"], 1)
        self.assertEqual(self.c(self.other_admin).post(f"{URL}{a}/read/").status_code, 404)

    def test_validation_messages(self):
        self.assertEqual(self.send(title="").status_code, 400)
        self.assertEqual(self.send(body="x" * 2001).status_code, 400)
        self.assertEqual(self.send(audience="aliens").status_code, 400)
        self.assertEqual(self.send(sms_text="x" * 460).status_code, 400)

    @mock.patch.dict(os.environ, SMS_ON)
    def test_retry_requeues_failures(self):
        with mock.patch("api.sms.send_bulk", side_effect=lambda nums, m: {n: ("failed", "down") for n in nums}):
            a = self.send(send_sms=True, audience="parents").data["id"]
        self.assertEqual(Announcement.objects.get(pk=a).status, "partial")
        r = self.c(self.admin).post(f"{URL}{a}/retry/")
        self.assertEqual(r.data["requeued_sms"], 2)
        self.assertEqual(Announcement.objects.get(pk=a).status, "sent")


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", MESSAGING_SYNC=True)
class PreferenceAndAlertEmailTests(TestCase):
    _user = Base._user
    setUp = Base.setUp

    def test_preferences_round_trip(self):
        c = APIClient()
        c.force_authenticate(self.parent)
        self.assertEqual(c.get("/api/me/alert-preferences/").data["email_alerts"], True)
        r = c.patch("/api/me/alert-preferences/", {"sms_alerts": False}, format="json")
        self.assertFalse(r.data["sms_alerts"])
        self.assertTrue(r.data["phone_valid"])
        self.assertEqual(c.patch("/api/me/alert-preferences/", {"sms_alerts": "no"}, format="json").status_code, 400)

    def test_admin_alert_is_emailed_unless_turned_off(self):
        from api.notify import notify_admins
        self.admin.email = "boss@x.ke"
        self.admin.save()
        notify_admins(self.school, "join_requested", "New staff request from Jane.")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["boss@x.ke"])
        NotificationPreference.objects.create(user=self.admin, email_alerts=False)
        notify_admins(self.school, "join_requested", "Another request.")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(Notification.objects.filter(recipient=self.admin).count(), 2)
