from rest_framework.test import APITestCase

from . import tests as base


class UnofficialAnalyticsTests(APITestCase):
    def setUp(self):
        base.AnalyticsTests.setUp(self)
    payload = base.WorkflowTests.payload

    def summary(self):
        self.client.force_authenticate(self.admin)
        url = f"/api/analytics/term-summary/{self.term.id}/"
        return self.client.get(url).json()

    def test_draft_is_unofficial_only(self):
        d = self.summary()
        self.assertEqual(d["subjects"], [])
        self.assertEqual(d["unofficial"]["draft"], 1)
        self.assertEqual(d["unofficial"]["subjects"][0]["average"], 70.0)

    def test_approved_moves_to_official(self):
        base.WorkflowTests.act(self, self.good, self.pk, "submit")
        base.WorkflowTests.act(self, self.admin, self.pk, "approve")
        d = self.summary()
        self.assertEqual(d["subjects"][0]["average"], 70.0)
        self.assertEqual(d["unofficial"]["subjects"], [])
        self.assertEqual(d["unofficial"]["draft"], 0)
