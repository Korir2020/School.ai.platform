import json
import os
import sqlite3
import tempfile
from pathlib import Path
from uuid import uuid4
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from api.offsite_backup import (
    _encrypt_file, _decrypt_file, _make_db_dump, _make_media_archive,
    _sign_manifest, verify_manifest, claim_next_run, _sanitize_sqlite_snapshot,
    process_run,
)
from schools.models import OffsiteBackupRun


class OffsiteBackupCryptoTests(APITestCase):
    def test_encrypted_file_and_signed_manifest_detect_tampering(self):
        key = os.urandom(32)
        mac = os.urandom(32)
        with tempfile.TemporaryDirectory() as temp:
            clear = Path(temp) / "clear"
            encrypted = Path(temp) / "encrypted"
            decoded = Path(temp) / "decoded"
            clear.write_bytes(b"fees, connect text, and audit contents\x00" * 100)
            info = _encrypt_file(str(clear), str(encrypted), key, "database")
            self.assertEqual(_decrypt_file(str(encrypted), str(decoded), key, "database"),
                             info["plaintext_sha256"])
            self.assertEqual(decoded.read_bytes(), clear.read_bytes())
            corrupt = bytearray(encrypted.read_bytes())
            corrupt[-1] ^= 1
            encrypted.write_bytes(corrupt)
            with self.assertRaises(Exception):
                _decrypt_file(str(encrypted), str(decoded), key, "database")

        manifest = _sign_manifest({
            "format": "marian-offsite-backup", "version": 1,
            "run_id": str(uuid4()), "objects": {},
        }, mac)
        self.assertEqual(verify_manifest(manifest, mac)["format"], "marian-offsite-backup")
        manifest["objects"]["database"] = {"ciphertext_sha256": "bad"}
        with self.assertRaises(RuntimeError):
            verify_manifest(manifest, mac)

    def test_sqlite_online_snapshot_contains_sensitive_application_tables(self):
        with tempfile.TemporaryDirectory() as temp:
            dump = os.path.join(temp, "database.sqlite3")
            self.assertEqual(_make_db_dump(dump), "sqlite")
            db = sqlite3.connect(dump)
            try:
                tables = {row[0] for row in db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")}
            finally:
                db.close()
        self.assertTrue({"schools_feepayment", "schools_connectpost", "schools_markauditlog"}.issubset(tables))

    def test_media_root_is_archived_separately(self):
        with tempfile.TemporaryDirectory() as temp:
            media = Path(temp) / "media"
            media.mkdir()
            (media / "report.pdf").write_bytes(b"sample media")
            bundle = Path(temp) / "media.tar.gz"
            with override_settings(MEDIA_ROOT=media):
                _make_media_archive(str(bundle))
            import tarfile
            with tarfile.open(bundle, "r:gz") as archive:
                self.assertEqual(archive.getnames(), ["media/report.pdf"])


class OffsiteBackupApiTests(APITestCase):
    def test_queue_and_history_are_superadmin_only(self):
        ordinary = User.objects.create_user("backup-ordinary", password="pass12345")
        self.client.force_authenticate(ordinary)
        self.assertEqual(self.client.get("/api/backups/offsite/status/").status_code, 403)
        self.assertEqual(self.client.post("/api/backups/offsite/trigger/").status_code, 403)

        admin = User.objects.create_superuser("backup-root", "root@example.test", "pass12345")
        self.client.force_authenticate(admin)
        status = self.client.get("/api/backups/offsite/status/")
        self.assertEqual(status.status_code, 200)
        self.assertIn("configured", status.json())
        self.assertFalse(status.json()["automatic_schedule_configured"])
        created = self.client.post("/api/backups/offsite/trigger/", {}, format="json")
        self.assertEqual(created.status_code, 202, created.content)
        run = OffsiteBackupRun.objects.get()
        self.assertEqual(run.status, "queued")
        self.assertEqual(run.requested_by, admin)
        history = self.client.get("/api/backups/offsite/history/")
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.json()["results"][0]["id"], str(run.id))

    def test_worker_lease_blocks_duplicate_claim_and_recovers_after_expiry(self):
        run = OffsiteBackupRun.objects.create()
        claimed = claim_next_run()
        self.assertEqual(claimed[0], run.id)
        self.assertIsNone(claim_next_run())
        run.refresh_from_db()
        old_token = run.lease_token
        run.lease_expires_at = timezone.now() - timedelta(seconds=1)
        run.save(update_fields=["lease_expires_at"])
        reclaimed = claim_next_run()
        self.assertEqual(reclaimed[0], run.id)
        self.assertNotEqual(reclaimed[1], old_token)

    def test_superadmin_can_requeue_only_failed_run(self):
        admin = User.objects.create_superuser("backup-retry-root", "retry@example.test", "pass12345")
        self.client.force_authenticate(admin)
        run = OffsiteBackupRun.objects.create(status="failed", error="connection failed")
        response = self.client.post(f"/api/backups/offsite/{run.id}/retry/", {}, format="json")
        self.assertEqual(response.status_code, 202, response.content)
        run.refresh_from_db()
        self.assertEqual(run.status, "queued")
        self.assertEqual(self.client.post(f"/api/backups/offsite/{run.id}/retry/").status_code, 409)


class BackupRecoverySafeguardTests(APITestCase):
    def test_sqlite_snapshot_sanitizer_removes_sessions_tokens_and_mfa_secrets(self):
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "snapshot.sqlite3"
            db = sqlite3.connect(db_path)
            for table in ("django_session", "token_blacklist_outstandingtoken",
                          "token_blacklist_blacklistedtoken", "schools_superadminsecurity"):
                db.execute(f'CREATE TABLE "{table}" (secret TEXT)')
                db.execute(f'INSERT INTO "{table}" VALUES (?)', ("private-secret",))
            db.commit(); db.close()
            _sanitize_sqlite_snapshot(db_path)
            db = sqlite3.connect(db_path)
            try:
                for table in ("django_session", "token_blacklist_outstandingtoken",
                              "token_blacklist_blacklistedtoken", "schools_superadminsecurity"):
                    self.assertEqual(db.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0], 0)
            finally:
                db.close()

    @patch("api.offsite_backup._upload_and_verify", side_effect=RuntimeError("temporary object-store outage"))
    def test_failed_backup_is_requeued_with_backoff_then_marks_final_failure(self, _upload):
        run = OffsiteBackupRun.objects.create(status="running", lease_token=uuid4(), attempts=1)
        with patch.dict(os.environ, {"BACKUP_RETRY_ATTEMPTS": "3", "BACKUP_RETRY_BASE_SECONDS": "1"}):
            self.assertEqual(process_run(run.id, run.lease_token), "queued")
        run.refresh_from_db()
        self.assertEqual(run.status, "queued")
        self.assertIsNotNone(run.retry_after)
        self.assertIn("temporary object-store outage", run.error)
        run.status = "running"; run.attempts = 3; run.lease_token = uuid4()
        run.save(update_fields=["status", "attempts", "lease_token"])
        with patch.dict(os.environ, {"BACKUP_RETRY_ATTEMPTS": "3", "BACKUP_RETRY_BASE_SECONDS": "1"}):
            self.assertEqual(process_run(run.id, run.lease_token), "failed")
        run.refresh_from_db()
        self.assertEqual(run.status, "failed")
        self.assertIsNotNone(run.finished_at)

    def test_media_restore_rejects_path_traversal(self):
        import tarfile
        with tempfile.TemporaryDirectory() as temp:
            archive_path = Path(temp) / "unsafe.tar.gz"
            member = Path(temp) / "payload"
            member.write_text("unsafe")
            with tarfile.open(archive_path, "w:gz") as archive:
                archive.add(member, arcname="media/../outside.txt")
            from schools.management.commands.restore_offsite_backup import _validate_media_tar
            with self.assertRaises(Exception):
                _validate_media_tar(archive_path, temp)

    def test_restore_audit_is_append_only_jsonl_without_secret_material(self):
        from schools.management.commands.restore_offsite_backup import _append_restore_audit
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp) / "restore-audit.jsonl"
            manifest = {"database_engine": "sqlite", "run_id": "backup-id"}
            _append_restore_audit(log, "restore_started", "backup-id", "/staging/db.sqlite3",
                                  "/staging/media", manifest)
            _append_restore_audit(log, "restore_completed", "backup-id", "/staging/db.sqlite3",
                                  "/staging/media", manifest)
            rows = [json.loads(line) for line in log.read_text().splitlines()]
            self.assertEqual([row["action"] for row in rows], ["restore_started", "restore_completed"])
            self.assertEqual(rows[0]["run_id"], "backup-id")
            self.assertNotIn("password", log.read_text().lower())

    def test_restore_command_writes_only_new_targets_and_records_success(self):
        import tarfile
        from django.core.management import call_command
        from django.core.management.base import CommandError
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            backup_db = root / "backup.sqlite3"
            db = sqlite3.connect(backup_db)
            db.execute("CREATE TABLE django_migrations (id INTEGER)")
            db.execute("CREATE TABLE schools_school (id INTEGER)")
            db.commit(); db.close()
            media_tar = root / "media.tar.gz"
            media_file = root / "logo.txt"
            media_file.write_text("school branding")
            with tarfile.open(media_tar, "w:gz") as archive:
                archive.add(media_file, arcname="media/logo.txt")
            target_db = root / "restored.sqlite3"
            target_media = root / "restored-media"
            audit = root / "audit.jsonl"
            manifest = {"database_engine": "sqlite", "run_id": "restore-test"}
            files = {"database": str(backup_db), "media": str(media_tar)}
            with patch("schools.management.commands.restore_offsite_backup.download_and_decrypt",
                       return_value=(None, manifest, files)):
                call_command("restore_offsite_backup", "restore-test",
                             target_database=str(target_db), media_staging_dir=str(target_media),
                             audit_log=str(audit), verbosity=0)
                self.assertFalse(target_db.exists())
                self.assertFalse(target_media.exists())
                call_command("restore_offsite_backup", "restore-test",
                             target_database=str(target_db), media_staging_dir=str(target_media),
                             yes=True, audit_log=str(audit), verbosity=0)
            self.assertTrue(target_db.exists())
            self.assertEqual((target_media / "logo.txt").read_text(), "school branding")
            rows = [json.loads(line) for line in audit.read_text().splitlines()]
            self.assertEqual(rows[-1]["action"], "restore_completed")
            self.assertEqual(sqlite3.connect(target_db).execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_restore_command_removes_invalid_sqlite_target_and_keeps_failure_audit(self):
        import tarfile
        from django.core.management import call_command
        from django.core.management.base import CommandError
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            backup_db = root / "invalid.sqlite3"
            backup_db.write_bytes(b"not a SQLite database")
            media_tar = root / "media.tar.gz"
            with tarfile.open(media_tar, "w:gz") as archive:
                pass
            target_db = root / "restored.sqlite3"
            target_media = root / "restored-media"
            audit = root / "audit.jsonl"
            manifest = {"database_engine": "sqlite", "run_id": "restore-test"}
            files = {"database": str(backup_db), "media": str(media_tar)}
            with patch("schools.management.commands.restore_offsite_backup.download_and_decrypt",
                       return_value=(None, manifest, files)):
                with self.assertRaises(Exception):
                    call_command("restore_offsite_backup", "restore-test",
                                 target_database=str(target_db), media_staging_dir=str(target_media),
                                 yes=True, audit_log=str(audit), verbosity=0)
            self.assertFalse(target_db.exists())
            rows = [json.loads(line) for line in audit.read_text().splitlines()]
            self.assertEqual(rows[-1]["action"], "restore_failed")

    @patch.dict(os.environ, {"OFFSITE_S3_BUCKET": "test", "OFFSITE_S3_ACCESS_KEY": "x",
                             "OFFSITE_S3_SECRET_KEY": "y", "BACKUP_ENCRYPTION_KEY": "z",
                             "BACKUP_MANIFEST_HMAC_KEY": "w"})
    def test_scheduled_enqueue_deduplicates_queued_run(self):
        from django.core.management import call_command
        call_command("enqueue_offsite_backup", minimum_interval_hours=23, verbosity=0)
        call_command("enqueue_offsite_backup", minimum_interval_hours=23, verbosity=0)
        self.assertEqual(OffsiteBackupRun.objects.count(), 1)
