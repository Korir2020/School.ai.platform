from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from api.connect_rules import ensure_default_channels
from schools.models import (
    ConnectAttachment,
    ConnectAvatar,
    ConnectChannel,
    ConnectPost,
    ConnectReport,
    School,
    SchoolAdminProfile,
    StaffProfile,
    TeacherProfile,
)

B = "/api/connect/"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


class ConnectFeePrivacyBoundaryTests(TestCase):
    def _user(self, username, **kwargs):
        return get_user_model().objects.create_user(
            username, f"{username}@example.com", "pw12345!", **kwargs
        )

    def setUp(self):
        self.school = School.objects.create(name="Boundary School", code="bound-school")
        self.other_school = School.objects.create(name="Other Boundary School", code="bound-other")
        self.admin = self._user("boundary_admin", first_name="Sam", last_name="Admin")
        SchoolAdminProfile.objects.create(user=self.admin, school=self.school)
        self.bursar = self._user("boundary_bursar")
        StaffProfile.objects.create(user=self.bursar, school=self.school, role="bursar")
        self.teacher = self._user("boundary_teacher")
        TeacherProfile.objects.create(user=self.teacher, school=self.school)
        self.root = get_user_model().objects.create_superuser(
            "boundary_root", "boundary_root@example.com", "pw12345!"
        )
        # Simulate a platform operator who also has a school profile: that must
        # never grant the operator access to school Connect content.
        SchoolAdminProfile.objects.create(user=self.root, school=self.school)
        ensure_default_channels(self.school.id)
        ensure_default_channels(self.other_school.id)
        self.notices = ConnectChannel.objects.get(school=self.school, kind="notices")
        self.community = ConnectChannel.objects.get(school=self.school, kind="community")
        self.other_community = ConnectChannel.objects.get(school=self.other_school, kind="community")
        self.post = ConnectPost.objects.create(
            channel=self.community, author=self.admin, body="Staff-authored post"
        )
        self.report = ConnectReport.objects.create(
            post=self.post, reporter=self.teacher, reason="Review this post"
        )
        self.attachment = ConnectAttachment.objects.create(
            post=self.post,
            name="note.pdf",
            content_type="application/pdf",
            size=5,
            data=b"%PDFx",
        )
        self.avatar = ConnectAvatar.objects.create(
            user=self.admin, content_type="image/png", size=len(PNG), data=PNG
        )

    def _client(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def test_superuser_with_school_profile_is_denied_all_connect_message_routes(self):
        client = self._client(self.root)
        actions = [
            client.get(B + "channels/"),
            client.get(f"{B}channels/{self.community.id}/posts/"),
            client.post(
                f"{B}channels/{self.community.id}/posts/",
                {"body": "A new user-authored note"},
                format="json",
            ),
            client.patch(f"{B}posts/{self.post.id}/", {"is_pinned": True}, format="json"),
            client.delete(f"{B}posts/{self.post.id}/"),
            client.post(f"{B}posts/{self.post.id}/ack/"),
            client.post(
                f"{B}posts/{self.post.id}/report/", {"reason": "Review"}, format="json"
            ),
            client.get(B + "reports/"),
            client.post(f"{B}reports/{self.report.id}/resolve/", {}, format="json"),
            client.get(B + "members/"),
            client.post(f"{B}members/{self.teacher.id}/mute/"),
            client.delete(f"{B}members/{self.teacher.id}/mute/"),
            client.get(f"{B}attachments/{self.attachment.id}/"),
            client.get(B + "avatar/"),
            client.post(
                B + "avatar/",
                {"file": SimpleUploadedFile("avatar.png", PNG, content_type="image/png")},
                format="multipart",
            ),
            client.delete(B + "avatar/"),
            client.get(f"{B}posts/{self.post.id}/avatar/"),
        ]
        self.assertEqual([response.status_code for response in actions], [403] * len(actions))
        self.assertTrue(ConnectPost.objects.filter(pk=self.post.pk).exists())
        self.assertFalse(ConnectPost.objects.filter(channel=self.community, author=self.root).exists())
        self.assertFalse(ConnectReport.objects.get(pk=self.report.pk).resolved)

    def test_other_school_admin_cannot_read_posts_or_attachments(self):
        other_admin = self._user("boundary_other_admin")
        SchoolAdminProfile.objects.create(user=other_admin, school=self.other_school)
        client = self._client(other_admin)
        self.assertEqual(client.get(f"{B}channels/{self.community.id}/posts/").status_code, 404)
        self.assertEqual(client.get(f"{B}attachments/{self.attachment.id}/").status_code, 404)
        self.assertEqual(client.get(f"{B}channels/{self.other_community.id}/posts/").status_code, 200)

    def test_default_channels_have_no_automatic_posts_and_authored_text_is_preserved(self):
        ensure_default_channels(self.school.id)
        self.assertEqual(
            list(ConnectChannel.objects.filter(school=self.school).values_list("name", flat=True)),
            ["School Notices", "Parents Community"],
        )
        self.assertEqual(ConnectPost.objects.filter(channel__school=self.school).count(), 1)
        self.assertEqual(ConnectPost.objects.filter(channel__school=self.other_school).count(), 0)
        body = "Fees and balances can be discussed; M-Pesa is one topic people may choose to mention."
        response = self._client(self.bursar).post(
            f"{B}channels/{self.community.id}/posts/", {"body": body}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["body"], body)
        self.assertEqual(ConnectPost.objects.get(pk=response.data["id"]).body, body)
        # Existing Connect access remains available to a school teacher too.
        self.assertEqual(
            self._client(self.teacher).get(f"{B}channels/{self.community.id}/posts/").status_code,
            200,
        )
