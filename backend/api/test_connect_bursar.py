from django.test import TestCase
from rest_framework.test import APIClient

from api.test_connect_views import B, ConnectApiTests as Base
from schools.models import StaffProfile


class BursarConnectTests(TestCase):
    _user = Base._user

    def setUp(self):
        Base.setUp(self)
        self.bursar = self._user("cv_bursar", first_name="Bea", last_name="Bursar")
        StaffProfile.objects.create(user=self.bursar, school=self.school, role="bursar")
        self.other_bursar = self._user("cv_other_bursar", first_name="Olu", last_name="Other")
        StaffProfile.objects.create(user=self.other_bursar, school=self.other, role="bursar")
        self.secretary = self._user("cv_secretary", first_name="Sam", last_name="Secretary")
        StaffProfile.objects.create(user=self.secretary, school=self.school, role="secretary")

    def client_for(self, user):
        c = APIClient()
        c.force_authenticate(user)
        return c

    def post(self, user, channel, body):
        return self.client_for(user).post(f"{B}channels/{channel.id}/posts/", {"body": body}, format="json")

    def test_bursar_can_open_connect(self):
        r = self.client_for(self.bursar).get(f"{B}channels/")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["me"]["role"], "bursar")
        self.assertFalse(r.data["me"]["is_admin"])
        self.assertGreaterEqual(len(r.data["channels"]), 2)

    def test_bursar_can_post_in_community(self):
        r = self.post(self.bursar, self.community, "Fee statements go out on Friday.")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["author_role"], "bursar")

    def test_bursar_cannot_post_in_notices(self):
        self.assertEqual(self.post(self.bursar, self.notices, "Hello").status_code, 403)

    def test_bursar_is_listed_for_admin(self):
        r = self.client_for(self.admin).get(f"{B}members/")
        self.assertEqual(r.status_code, 200, r.data)
        rows = [m for m in r.data["members"] if m["role"] == "bursar"]
        self.assertEqual([m["name"] for m in rows], ["Bea Bursar"])

    def test_other_school_bursar_cannot_read_this_school(self):
        c = self.client_for(self.other_bursar)
        self.assertIn(c.get(f"{B}channels/{self.community.id}/posts/").status_code, (403, 404))
        self.assertIn(self.post(self.other_bursar, self.community, "Hi").status_code, (403, 404))

    def test_secretary_still_has_no_connect(self):
        self.assertEqual(self.client_for(self.secretary).get(f"{B}channels/").status_code, 403)

    def test_admin_can_mute_a_bursar(self):
        r = self.client_for(self.admin).post(f"{B}members/{self.bursar.id}/mute/")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(self.post(self.bursar, self.community, "Hello again").status_code, 403)
