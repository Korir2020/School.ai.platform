from rest_framework.test import APITestCase


class HealthTests(APITestCase):
    def test_anonymous_gets_ok(self):
        r = self.client.get("/api/health/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"status": "ok"})

    def test_only_get_allowed(self):
        self.assertEqual(self.client.post("/api/health/").status_code, 405)
