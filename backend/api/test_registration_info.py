from django.core.cache import cache
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from schools.models import MarkAuditLog, School, SchoolRegistration
from api.test_school_registration import PW, good

User = get_user_model()
SUBMIT = "/api/school-registration/"
STATUS = "/api/school-registration/status/"
RESPOND = "/api/school-registration/respond/"


class InfoWorkflowTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.root = User.objects.create_superuser("root", "root@example.com", "Root-secure-pass")
        self.admin = User.objects.create_user("schooladmin", password=PW)
        r = self.client.post(SUBMIT, good(), format="json")
        self.reg = SchoolRegistration.objects.get(reference=r.data["reference"])
        self.reg.status = "verified"
        self.reg.verification_status = "verified"
        self.reg.save(update_fields=["status", "verification_status"])
        self.url = "/api/admin/school-registrations/%s/action/" % self.reg.id
        self.ident = {"reference": self.reg.reference, "username": self.reg.administrator_username}

    def ask(self, message="Please send proof of registration."):
        self.client.force_authenticate(self.root)
        return self.client.post(self.url, {"action": "request_information", "message": message}, format="json")

    def reply(self, message="Certificate number 12345.", **over):
        return self.client.post(RESPOND, {**self.ident, "message": message, **over}, format="json")

    def act(self, action, **extra):
        self.client.force_authenticate(self.root)
        return self.client.post(self.url, {"action": action, **extra}, format="json")

    def status(self):
        self.reg.refresh_from_db()
        return self.reg.status

    def test_non_superadmin_cannot_request(self):
        self.client.force_authenticate(self.admin)
        r = self.client.post(self.url, {"action": "request_information", "message": "x"}, format="json")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.status(), "verified")

    def test_message_is_required(self):
        self.assertEqual(self.ask("   ").status_code, 400)
        self.assertEqual(self.ask("x" * 2001).status_code, 400)
        self.assertEqual(self.status(), "verified")

    def test_request_sets_status_and_is_audited(self):
        r = self.ask("Send the certificate.")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(self.status(), "needs_information")
        self.assertEqual(self.reg.info_request_message, "Send the certificate.")
        self.assertTrue(MarkAuditLog.objects.filter(action="school_reg_info_asked").exists())
        s = self.client.post(STATUS, self.ident, format="json")
        self.assertEqual(s.data["info_request_message"], "Send the certificate.")

    def test_request_needs_verified_email(self):
        SchoolRegistration.objects.filter(pk=self.reg.pk).update(status="pending_verification", verification_status="unverified")
        self.assertEqual(self.ask().status_code, 409)

    def test_cannot_request_twice_or_on_finished(self):
        self.assertEqual(self.ask().status_code, 200)
        self.assertEqual(self.ask().status_code, 409)
        SchoolRegistration.objects.filter(pk=self.reg.pk).update(status="rejected")
        self.assertEqual(self.ask().status_code, 409)

    def test_approve_blocked_while_waiting_but_reject_allowed(self):
        self.ask()
        self.assertEqual(self.act("approve").status_code, 409)
        self.assertEqual(School.objects.count(), 0)
        self.assertEqual(self.act("reject", reason="No reply needed.").status_code, 200)
        self.assertEqual(self.status(), "rejected")

    def test_reply_returns_application_to_review(self):
        self.ask()
        r = self.reply()
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(self.status(), "pending_approval")
        self.assertEqual(self.reg.info_response_message, "Certificate number 12345.")
        self.assertEqual(r.data["status"], "pending_approval")
        self.assertTrue(MarkAuditLog.objects.filter(action="school_reg_info_reply").exists())

    def test_reply_validation(self):
        self.ask()
        self.assertEqual(self.reply("  ").status_code, 400)
        self.assertEqual(self.reply("x" * 2001).status_code, 400)
        self.assertEqual(self.reply(username="nobody").status_code, 404)
        self.assertEqual(self.status(), "needs_information")

    def test_reply_rejected_when_nothing_requested(self):
        self.assertEqual(self.reply().status_code, 409)
        self.assertEqual(self.status(), "verified")

    def test_reply_cannot_be_sent_twice(self):
        self.ask()
        self.assertEqual(self.reply().status_code, 200)
        self.assertEqual(self.reply("again").status_code, 409)

    def test_approve_works_after_reply_and_more_info_can_be_requested(self):
        self.ask()
        self.reply()
        self.assertEqual(self.ask("One more thing.").status_code, 200)
        self.reply("Done.")
        r = self.act("approve")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(self.status(), "approved")
