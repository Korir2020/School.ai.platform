"""Numeric scores include zero; absence is represented by a separate disposition."""
from rest_framework.test import APITestCase

from . import tests as base
from schools.models import Performance


class MarkRangeTests(APITestCase):
    payload = base.MarksEntryTests.payload

    def setUp(self):
        base.MarksEntryTests.setUp(self)
        self.client.force_authenticate(self.good)

    def post(self, marks):
        return self.client.post(
            "/api/performance/", self.payload(marks=marks), format="json")

    def test_rejected_values(self):
        for bad in (-1, 100.01, 101, 1000, "abc", None):
            r = self.post(bad)
            self.assertEqual(r.status_code, 400, f"{bad!r} must be rejected")
        self.assertEqual(Performance.objects.count(), 0)

    def test_accepted_boundaries(self):
        for good in (0, "0", 1, 1.0, 100, 50.5):
            Performance.objects.all().delete()
            r = self.post(good)
            self.assertEqual(r.status_code, 201, f"{good!r} must be accepted")

    def test_edit_to_zero_is_valid_and_old_kept_after_invalid_input(self):
        pid = self.post(55).json()["id"]
        url = f"/api/performance/{pid}/"
        for bad in (101,):
            r = self.client.patch(url, {"marks": bad}, format="json")
            self.assertEqual(r.status_code, 400)
        self.assertEqual(float(Performance.objects.get(pk=pid).marks), 55.0)
        r = self.client.patch(url, {"marks": 0}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(float(Performance.objects.get(pk=pid).marks), 0.0)

    def test_database_accepts_zero_and_blocks_negative_without_serializer(self):
        from django.db import IntegrityError, transaction
        pid = self.post(55).json()["id"]
        self.assertEqual(Performance.objects.filter(pk=pid).update(marks=0), 1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Performance.objects.filter(pk=pid).update(marks=-1)
