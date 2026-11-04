import gzip
import io
import json
import os
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from rest_framework.test import APIClient

from api.backup import build_full_backup, read_backup, school_export
from api.test_connect_views import ConnectApiTests as Base
from schools.models import MarkAuditLog, Student


class BackupTests(TestCase):
    _user = Base._user
    setUp = Base.setUp

    def c(self, user):
        c = APIClient()
        c.force_authenticate(user)
        return c

    def test_full_backup_round_trip_checks(self):
        blob, meta = build_full_backup()
        doc, report = read_backup(blob)
        self.assertTrue(report["ok"], report)
        self.assertEqual(meta["counts"]["schools.student"], Student.objects.count())
        self.assertNotIn("contenttypes.contenttype", meta["counts"])

    def test_tampered_backup_rejected(self):
        blob, _ = build_full_backup()
        doc = json.loads(gzip.decompress(blob))
        doc["objects"][0]["fields"]["name"] = "Hacked"
        _, report = read_backup(json.dumps(doc).encode())
        self.assertFalse(report["ok"])
        self.assertIn("checksum", report["problems"][0])
        _, junk = read_backup(b"not a backup")
        self.assertFalse(junk["ok"])

    def test_only_superadmin_downloads_and_validates(self):
        for u in (self.admin, self.teacher, self.parent):
            self.assertEqual(self.c(u).get("/api/backups/full/").status_code, 403)
        r = self.c(self.root).get("/api/backups/full/")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r["Content-Disposition"].startswith("attachment"))
        self.assertTrue(MarkAuditLog.objects.filter(action="backup_downloaded").exists())
        up = SimpleUploadedFile("b.json.gz", r.content)
        v = self.c(self.root).post("/api/backups/validate/", {"file": up}, format="multipart")
        self.assertTrue(v.data["ok"], v.data)

    def test_restore_command_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            call_command("backup_data", output_dir=d, stdout=io.StringIO())
            path = os.path.join(d, os.listdir(d)[0])
            before = Student.objects.count()
            Student.objects.all().delete()
            with self.assertRaises(CommandError):
                call_command("restore_data", path, yes=True, stdout=io.StringIO(), stderr=io.StringIO())
            call_command("restore_data", path, yes=True, replace=True, stdout=io.StringIO(), stderr=io.StringIO())
            self.assertEqual(Student.objects.count(), before)

    def test_backup_keeps_only_recent_files(self):
        with tempfile.TemporaryDirectory() as d:
            for n in ("marian-backup-20260101-0000.json.gz", "marian-backup-20260102-0000.json.gz"):
                open(os.path.join(d, n), "wb").close()
            call_command("backup_data", output_dir=d, keep=2, stdout=io.StringIO())
            self.assertEqual(len(os.listdir(d)), 2)
            self.assertNotIn("marian-backup-20260101-0000.json.gz", os.listdir(d))

    def test_school_export_is_scoped_and_has_no_passwords(self):
        doc = school_export(self.school)
        names = {r["fields"]["admission_number"] for r in doc["data"]["Student"]}
        self.assertEqual(names, {"A1", "A2"})
        dumped = json.dumps(doc, default=str)
        self.assertNotIn("Other Con", dumped)
        self.assertNotIn("password", dumped)
        self.assertIn("Enrollment", doc["data"])

    def test_school_export_endpoint_admin_only(self):
        self.assertEqual(self.c(self.teacher).get("/api/school/export/").status_code, 403)
        r = self.c(self.admin).get("/api/school/export/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(json.loads(r.content)["meta"]["school"], "Con School")
