from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from api.test_connect_views import B, ConnectApiTests as Base

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def png(name="me.png", extra=0):
    return SimpleUploadedFile(name, PNG + b"\x00" * extra, content_type="image/png")


class AvatarTests(TestCase):
    _user = Base._user
    setUp = Base.setUp

    def client_for(self, user):
        c = APIClient()
        c.force_authenticate(user)
        return c

    def upload(self, who, f):
        return self.client_for(who).post(f"{B}avatar/", {"file": f}, format="multipart")

    def make_post(self):
        r = self.client_for(self.admin).post(
            f"{B}channels/{self.community.id}/posts/", {"body": "Hello"}, format="multipart"
        )
        self.assertEqual(r.status_code, 201, r.data)
        return r.data["id"]

    def test_upload_download_replace_delete(self):
        pid = self.make_post()
        url = f"{B}posts/{pid}/avatar/"
        self.assertEqual(self.client_for(self.teacher).get(url).status_code, 404)
        self.assertEqual(self.upload(self.admin, png()).status_code, 200)
        for who in (self.teacher, self.parent, self.admin):
            d = self.client_for(who).get(url)
            self.assertEqual(d.status_code, 200)
            self.assertEqual(d["Content-Type"], "image/png")
            self.assertEqual(d.content, PNG)
        self.assertEqual(self.upload(self.admin, png(extra=5)).status_code, 200)
        self.assertEqual(self.client_for(self.teacher).get(url).content, PNG + b"\x00" * 5)
        d = self.client_for(self.admin).delete(f"{B}avatar/")
        self.assertEqual(d.status_code, 204)
        self.assertEqual(self.client_for(self.teacher).get(url).status_code, 404)

    def test_rejects_big_and_wrong_type(self):
        self.assertEqual(self.upload(self.admin, png(extra=1024 * 1024)).status_code, 400)
        bad = SimpleUploadedFile("x.png", b"hello world", content_type="image/png")
        self.assertEqual(self.upload(self.admin, bad).status_code, 400)
        r = self.client_for(self.admin).post(f"{B}avatar/", {}, format="multipart")
        self.assertEqual(r.status_code, 400)

    def test_requires_login(self):
        self.assertIn(APIClient().post(f"{B}avatar/").status_code, (401, 403))

    def test_get_own_picture(self):
        c = self.client_for(self.admin)
        self.assertEqual(c.get(f"{B}avatar/").status_code, 404)
        self.assertEqual(self.upload(self.admin, png()).status_code, 200)
        d = c.get(f"{B}avatar/")
        self.assertEqual(d.status_code, 200)
        self.assertEqual(d.content, PNG)
        self.assertEqual(self.client_for(self.teacher).get(f"{B}avatar/").status_code, 404)
