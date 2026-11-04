from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from api.test_connect_views import B, ConnectApiTests as Base

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


def jpg(name="photo.jpg", extra=0):
    return SimpleUploadedFile(name, JPEG + b"\x00" * extra, content_type="image/jpeg")


class AttachmentTests(TestCase):
    _user = Base._user
    setUp = Base.setUp

    def client_for(self, user):
        c = APIClient()
        c.force_authenticate(user)
        return c

    def post(self, files, body="Hello"):
        return self.client_for(self.admin).post(
            f"{B}channels/{self.community.id}/posts/",
            {"body": body, "files": files},
            format="multipart",
        )

    def test_photo_uploads_and_members_download(self):
        r = self.post([jpg()])
        self.assertEqual(r.status_code, 201, r.data)
        att = r.data["attachments"][0]
        self.assertEqual(att["name"], "photo.jpg")
        self.assertEqual(att["type"], "image/jpeg")
        for who in (self.teacher, self.parent, self.admin):
            d = self.client_for(who).get(f"{B}attachments/{att['id']}/")
            self.assertEqual(d.status_code, 200)
            self.assertEqual(d["Content-Type"], "image/jpeg")
            self.assertEqual(d.content, JPEG)

    def test_photo_only_message_is_allowed(self):
        r = self.post([jpg()], body="")
        self.assertEqual(r.status_code, 201, r.data)

    def test_fake_file_is_rejected(self):
        fake = SimpleUploadedFile("virus.jpg", b"MZ this is not a photo", content_type="image/jpeg")
        r = self.post([fake])
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["error"], "bad_file")

    def test_over_five_mb_is_rejected(self):
        r = self.post([jpg("big.jpg", extra=5 * 1024 * 1024)])
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["error"], "file_too_big")

    def test_fifth_file_is_rejected(self):
        r = self.post([jpg(f"p{i}.jpg") for i in range(5)])
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["error"], "too_many_files")

    def test_other_school_and_outsiders_cannot_download(self):
        att = self.post([jpg()]).data["attachments"][0]
        url = f"{B}attachments/{att['id']}/"
        self.assertEqual(self.client_for(self.other_admin).get(url).status_code, 404)
        self.assertEqual(self.client_for(self.stranger).get(url).status_code, 403)
        self.assertEqual(APIClient().get(url).status_code, 401)

    def test_hidden_post_files_are_closed_to_non_admins(self):
        r = self.post([jpg()])
        att = r.data["attachments"][0]
        h = self.client_for(self.admin).patch(f"{B}posts/{r.data['id']}/", {"hidden": True}, format="json")
        self.assertEqual(h.status_code, 200, h.data)
        url = f"{B}attachments/{att['id']}/"
        self.assertEqual(self.client_for(self.teacher).get(url).status_code, 404)
        self.assertEqual(self.client_for(self.admin).get(url).status_code, 200)
