import io
import stat
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from PIL import Image
from pypdf import PdfReader, PdfWriter
from rest_framework.test import APITestCase

from learning.asset_storage import (
    PrivateAssetStorageUnavailable,
    get_private_asset_storage,
    scan_asset_bytes,
)
from learning.models import LearningPrivateAsset, LearningProfile, LearningResource
from schools.models import School, SchoolAdminProfile, Student, TeacherProfile

User = get_user_model()
STUDIO = "/api/learning/v1/studio/"
CATALOG = "/api/learning/v1/catalog/"


class DeclaredPrivateDurableStorage:
    is_private = True
    is_durable = True

    def save(self, name, content):
        return name

    def open(self, name, mode="rb"):
        raise FileNotFoundError(name)

    def delete(self, name):
        return None


class UndeclaredPublicStorage(DeclaredPrivateDurableStorage):
    is_private = False


class LearningPrivateAssetApiTests(APITestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.private_root = Path(self.temp.name) / "private"
        self.media_root = Path(self.temp.name) / "public-media"
        self.setting_override = override_settings(
            DEBUG=True,
            MEDIA_ROOT=self.media_root,
            LEARNING_PRIVATE_ASSET_ROOT=self.private_root,
            LEARNING_PRIVATE_ASSET_STORAGE_BACKEND="",
            LEARNING_ASSET_SCANNER_BINARY="",
        )
        self.setting_override.enable()
        self.addCleanup(self.setting_override.disable)

        self.school = School.objects.create(name="Asset School", code="ASSET")
        self.other_school = School.objects.create(name="Other Asset School", code="OASSET")
        self.teacher = self.make_teacher("asset_teacher", self.school)
        self.other_teacher = self.make_teacher("other_asset_teacher", self.school)
        self.other_admin = self.make_admin("other_asset_admin", self.other_school)
        self.admin = self.make_admin("asset_admin", self.school)
        self.deputy = self.make_admin("asset_deputy", self.school, deputy=True)
        self.resource = self.make_resource()
        self.client.force_authenticate(self.teacher)

    @staticmethod
    def make_teacher(username, school):
        user = User.objects.create_user(username, password="Asset!123456")
        TeacherProfile.objects.create(user=user, school=school)
        return user

    @staticmethod
    def make_admin(username, school, deputy=False):
        user = User.objects.create_user(username, password="Asset!123456")
        SchoolAdminProfile.objects.create(user=user, school=school, is_deputy=deputy)
        return user

    def make_resource(self, **overrides):
        fields = {
            "scope": "school",
            "school": self.school,
            "author": self.teacher,
            "title": "A private learning resource",
            "summary": "Created for secure asset tests.",
            "body": "A short original lesson.",
            "resource_type": "lesson",
            "origin": "marian",
            "language_code": "en",
            "source_name": "Teacher-created resource",
            "license_name": "Marian-owned draft",
            "attribution": "Created by the school teacher.",
            "status": "draft",
        }
        fields.update(overrides)
        return LearningResource.objects.create(**fields)

    @staticmethod
    def png_bytes(size=(24, 16), color=(20, 120, 220)):
        buffer = io.BytesIO()
        Image.new("RGB", size, color).save(buffer, format="PNG")
        return buffer.getvalue()

    def upload(self, resource=None, data=None, filename="asset.png", media_type="image/png"):
        resource = resource or self.resource
        data = data if data is not None else self.png_bytes()
        file = SimpleUploadedFile(filename, data, content_type=media_type)
        return self.client.post(
            f"{STUDIO}resources/{resource.pk}/assets/",
            {"file": file},
            format="multipart",
        )

    def clean_scan(self):
        return patch(
            "learning.assets_api.scan_asset_bytes",
            return_value=("clean", timezone.now()),
        )

    def create_learner(self, school, username, admission_number):
        student = Student.objects.create(
            school=school,
            first_name="Nia",
            last_name="Learner",
            admission_number=admission_number,
            date_of_birth=date(2010, 5, 5),
        )
        user = User.objects.create_user(username)
        LearningProfile.objects.create(
            user=user,
            account_kind="school_student",
            school=school,
            student=student,
            age_band="10_17",
            consent_state="verified",
            locale="en",
        )
        return user

    def test_clean_upload_is_private_normalized_and_downloaded_with_safe_headers(self):
        original = self.png_bytes()
        with self.clean_scan():
            response = self.upload(data=original, filename="student supplied name.png")
        self.assertEqual(response.status_code, 201, response.content)
        payload = response.json()
        self.assertEqual(payload["scan_state"], "clean")
        self.assertTrue(payload["download_available"])
        self.assertNotIn("storage_name", payload)
        self.assertNotIn("student supplied name", response.content.decode())

        asset = LearningPrivateAsset.objects.get(pk=payload["id"])
        stored = self.private_root / asset.storage_name
        self.assertTrue(stored.is_file())
        self.assertNotEqual(stored.resolve(), self.media_root.resolve())
        self.assertTrue(self.private_root.resolve() not in self.media_root.resolve().parents)
        self.assertEqual(stat.S_IMODE(stored.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.private_root.stat().st_mode), 0o700)
        self.assertNotEqual(asset.sha256, "")

        public_media_path = "/media/" + asset.storage_name
        self.assertEqual(self.client.get(public_media_path).status_code, 404)
        download = self.client.get(
            f"{STUDIO}resources/{self.resource.pk}/assets/{asset.pk}/download/"
        )
        self.assertEqual(download.status_code, 200)
        self.assertTrue(download["Content-Disposition"].startswith("attachment;"))
        self.assertEqual(download["Content-Type"], "application/octet-stream")
        self.assertEqual(download["Cache-Control"], "private, no-store, max-age=0")
        self.assertEqual(download["X-Content-Type-Options"], "nosniff")
        self.assertEqual(download["X-Frame-Options"], "DENY")
        self.assertEqual(b"".join(download.streaming_content)[:8], b"\x89PNG\r\n\x1a\n")

    def test_missing_scanner_quarantines_and_blocks_download_and_submission(self):
        response = self.upload()
        self.assertEqual(response.status_code, 201, response.content)
        asset = LearningPrivateAsset.objects.get(pk=response.json()["id"])
        self.assertEqual(asset.scan_state, "quarantined")
        self.assertIsNone(asset.scanned_at)
        self.assertFalse(response.json()["download_available"])
        self.assertEqual(
            self.client.get(f"{STUDIO}resources/{self.resource.pk}/assets/{asset.pk}/download/").status_code,
            404,
        )
        submitted = self.client.post(f"{STUDIO}resources/{self.resource.pk}/submit/", {}, format="json")
        self.assertEqual(submitted.status_code, 400)
        self.assertIn("malware scanner", submitted.json()["detail"])
        self.assertEqual(LearningResource.objects.get(pk=self.resource.pk).status, "draft")

    def test_infected_scan_is_never_delivered_or_submitted(self):
        with patch(
            "learning.assets_api.scan_asset_bytes",
            return_value=("infected", timezone.now()),
        ):
            response = self.upload()
        self.assertEqual(response.status_code, 201)
        asset = LearningPrivateAsset.objects.get(pk=response.json()["id"])
        self.assertEqual(asset.scan_state, "infected")
        self.assertEqual(
            self.client.get(f"{STUDIO}resources/{self.resource.pk}/assets/{asset.pk}/download/").status_code,
            404,
        )
        submit = self.client.post(f"{STUDIO}resources/{self.resource.pk}/submit/", {}, format="json")
        self.assertEqual(submit.status_code, 400)
        self.assertEqual(LearningResource.objects.get(pk=self.resource.pk).status, "draft")

    def test_scan_exception_fails_closed_in_quarantine(self):
        with patch("learning.assets_api.scan_asset_bytes", side_effect=TimeoutError("scanner timeout")):
            response = self.upload()
        self.assertEqual(response.status_code, 201)
        asset = LearningPrivateAsset.objects.get(pk=response.json()["id"])
        self.assertEqual(asset.scan_state, "quarantined")
        self.assertIsNone(asset.scanned_at)

    def test_malformed_and_unsupported_files_are_rejected_by_bytes_not_client_mime(self):
        for data, name, content_type in (
            (b"<svg onload=alert(1)>", "image.svg", "image/png"),
            (b"PK\x03\x04archive", "file.pdf", "application/pdf"),
            (b"%PDF-1.7\nnot a pdf", "broken.pdf", "application/pdf"),
        ):
            with self.subTest(name=name):
                response = self.upload(data=data, filename=name, media_type=content_type)
                self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(LearningPrivateAsset.objects.count(), 0)

    def test_oversized_and_overdimension_images_are_rejected(self):
        oversized = b"x" * (10 * 1024 * 1024 + 1)
        response = self.upload(data=oversized, filename="large.png")
        self.assertEqual(response.status_code, 413)
        huge_dimension = self.png_bytes(size=(10001, 1))
        response = self.upload(data=huge_dimension)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(LearningPrivateAsset.objects.count(), 0)

    def test_pdf_is_rewritten_without_actions_or_attachments(self):
        writer = PdfWriter()
        writer.add_blank_page(width=300, height=300)
        writer.add_js("app.alert('unsafe')")
        writer.add_attachment("payload.txt", b"embedded payload")
        source = io.BytesIO()
        writer.write(source)
        with patch(
            "learning.assets_api.scan_asset_bytes",
            return_value=("clean", timezone.now()),
        ):
            response = self.upload(
                data=source.getvalue(), filename="unsafe.pdf", media_type="application/pdf",
            )
        self.assertEqual(response.status_code, 201, response.content)
        asset = LearningPrivateAsset.objects.get(pk=response.json()["id"])
        self.assertEqual(asset.content_type, "application/pdf")
        with (self.private_root / asset.storage_name).open("rb") as stored:
            reader = PdfReader(stored, strict=True)
            self.assertEqual(len(reader.pages), 1)
            self.assertNotIn("/OpenAction", reader.root_object)
            self.assertNotIn("/Names", reader.root_object)
            self.assertNotIn("/Annots", reader.pages[0])

    def test_asset_authorization_is_tenant_and_author_scoped(self):
        self.client.force_authenticate(self.other_teacher)
        self.assertEqual(
            self.client.get(f"{STUDIO}resources/{self.resource.pk}/assets/").status_code,
            404,
        )
        self.client.force_authenticate(self.other_admin)
        self.assertEqual(
            self.client.get(f"{STUDIO}resources/{self.resource.pk}/assets/").status_code,
            404,
        )
        self.client.force_authenticate(self.deputy)
        self.assertEqual(
            self.client.get(f"{STUDIO}resources/{self.resource.pk}/assets/").status_code,
            403,
        )
        self.client.force_authenticate(self.admin)
        self.assertEqual(
            self.client.get(f"{STUDIO}resources/{self.resource.pk}/assets/").status_code,
            200,
        )

    def test_deletion_revokes_access_before_cleanup_and_retry_is_idempotent(self):
        with self.clean_scan():
            uploaded = self.upload()
        asset = LearningPrivateAsset.objects.get(pk=uploaded.json()["id"])
        stored = self.private_root / asset.storage_name
        version_before_delete = LearningResource.objects.get(pk=self.resource.pk).version
        storage = get_private_asset_storage()
        with patch("learning.assets_api.get_private_asset_storage", return_value=storage):
            with patch.object(storage, "delete", side_effect=OSError("storage unavailable")):
                failed_cleanup = self.client.delete(
                    f"{STUDIO}resources/{self.resource.pk}/assets/{asset.pk}/"
                )
        self.assertEqual(failed_cleanup.status_code, 503)
        asset.refresh_from_db()
        self.assertEqual(asset.scan_state, "deleted")
        self.assertIsNotNone(asset.deleted_at)
        self.assertTrue(stored.exists())
        self.assertEqual(
            self.client.get(f"{STUDIO}resources/{self.resource.pk}/assets/{asset.pk}/download/").status_code,
            404,
        )
        version_after_first_delete = LearningResource.objects.get(pk=self.resource.pk).version
        self.assertEqual(version_after_first_delete, version_before_delete + 1)
        retried = self.client.delete(f"{STUDIO}resources/{self.resource.pk}/assets/{asset.pk}/")
        self.assertEqual(retried.status_code, 204)
        self.assertFalse(stored.exists())
        repeated = self.client.delete(f"{STUDIO}resources/{self.resource.pk}/assets/{asset.pk}/")
        self.assertEqual(repeated.status_code, 204)
        self.assertEqual(LearningResource.objects.get(pk=self.resource.pk).version, version_after_first_delete)

    def test_resource_state_is_rechecked_after_storage_write(self):
        storage = get_private_asset_storage()
        real_save = storage.save

        def save_then_change_status(name, content):
            stored_name = real_save(name, content)
            LearningResource.objects.filter(pk=self.resource.pk).update(status="in_review")
            return stored_name

        with patch("learning.assets_api.get_private_asset_storage", return_value=storage):
            with patch.object(storage, "save", side_effect=save_then_change_status):
                response = self.upload()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(LearningPrivateAsset.objects.count(), 0)
        self.assertFalse(any(self.private_root.rglob("*.png")))

    def test_catalogue_delivers_only_clean_published_assets_for_visible_learners(self):
        file_resource = self.make_resource(title="File-only study guide", body="")
        with self.clean_scan():
            uploaded = self.upload(resource=file_resource)
        asset = LearningPrivateAsset.objects.get(pk=uploaded.json()["id"])
        file_resource.status = "published"
        file_resource.published_at = timezone.now()
        file_resource.reviewed_by = self.admin
        file_resource.reviewed_at = timezone.now()
        file_resource.save(update_fields=["status", "published_at", "reviewed_by", "reviewed_at"])
        learner = self.create_learner(self.school, "asset_learner", "AS-001")

        self.client.force_authenticate(learner)
        listing = self.client.get(f"{CATALOG}resources/")
        self.assertEqual(listing.status_code, 200, listing.content)
        file_item = next(row for row in listing.json()["results"] if row["id"] == file_resource.pk)
        self.assertEqual(len(file_item["private_assets"]), 1)
        self.assertEqual(file_item["private_assets"][0]["id"], asset.pk)
        self.assertNotIn("storage_name", listing.content.decode())

        detail = self.client.get(f"{CATALOG}resources/{file_resource.pk}/")
        self.assertEqual(detail.status_code, 200, detail.content)
        self.assertFalse(detail.json()["private_asset_pending"])
        link = file_item["private_assets"][0]["download_url"]
        download = self.client.get(link)
        self.assertEqual(download.status_code, 200)
        self.assertEqual(b"".join(download.streaming_content)[:8], b"\x89PNG\r\n\x1a\n")

        foreign_learner = self.create_learner(self.other_school, "foreign_asset_learner", "OAS-001")
        self.client.force_authenticate(foreign_learner)
        foreign = self.client.get(link)
        self.assertEqual(foreign.status_code, 404)

    def test_file_only_resource_without_clean_asset_stays_hidden(self):
        file_resource = self.make_resource(title="Unattached file-only item", body="")
        file_resource.status = "published"
        file_resource.published_at = timezone.now()
        file_resource.reviewed_by = self.admin
        file_resource.reviewed_at = timezone.now()
        file_resource.save(update_fields=["status", "published_at", "reviewed_by", "reviewed_at"])
        learner = self.create_learner(self.school, "asset_learner_no_file", "AS-002")
        self.client.force_authenticate(learner)
        response = self.client.get(f"{CATALOG}resources/")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(file_resource.pk, {row["id"] for row in response.json()["results"]})

    def test_production_without_private_backend_fails_closed(self):
        with override_settings(DEBUG=False, LEARNING_PRIVATE_ASSET_STORAGE_BACKEND=""):
            response = self.upload()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(LearningPrivateAsset.objects.count(), 0)
        self.assertFalse(self.private_root.exists())

    def test_production_backend_must_attest_private_and_durable(self):
        with override_settings(
            DEBUG=False,
            LEARNING_PRIVATE_ASSET_STORAGE_BACKEND=(
                "learning.test_assets_api.DeclaredPrivateDurableStorage"
            ),
        ):
            storage = get_private_asset_storage()
            self.assertIsInstance(storage, DeclaredPrivateDurableStorage)
        with override_settings(
            DEBUG=False,
            LEARNING_PRIVATE_ASSET_STORAGE_BACKEND=(
                "learning.test_assets_api.UndeclaredPublicStorage"
            ),
        ):
            with self.assertRaises(PrivateAssetStorageUnavailable):
                get_private_asset_storage()

    def test_scanner_only_clears_on_zero_exit_code(self):
        with override_settings(LEARNING_ASSET_SCANNER_BINARY="/bin/true"):
            clean_state, clean_at = scan_asset_bytes(b"safe bytes", ".bin")
        self.assertEqual(clean_state, "clean")
        self.assertIsNotNone(clean_at)

        with override_settings(LEARNING_ASSET_SCANNER_BINARY="/bin/false"):
            infected_state, infected_at = scan_asset_bytes(b"test bytes", ".bin")
        self.assertEqual(infected_state, "infected")
        self.assertIsNotNone(infected_at)

        scanner = Path(self.temp.name) / "scanner-error"
        scanner.write_text("#!/bin/sh\nexit 2\n", encoding="utf-8")
        scanner.chmod(0o700)
        with override_settings(LEARNING_ASSET_SCANNER_BINARY=str(scanner)):
            error_state, error_at = scan_asset_bytes(b"unknown result", ".bin")
        self.assertEqual(error_state, "quarantined")
        self.assertIsNone(error_at)

    def test_local_storage_rejects_public_media_overlap(self):
        with override_settings(LEARNING_PRIVATE_ASSET_ROOT=self.media_root / "assets"):
            with self.assertRaises(PrivateAssetStorageUnavailable):
                get_private_asset_storage()

    def test_live_resource_must_be_archived_before_admin_asset_cleanup(self):
        with self.clean_scan():
            uploaded = self.upload()
        asset = LearningPrivateAsset.objects.get(pk=uploaded.json()["id"])
        stored = self.private_root / asset.storage_name
        resource = LearningResource.objects.get(pk=self.resource.pk)
        resource.status = "published"
        resource.published_at = timezone.now()
        resource.reviewed_by = self.admin
        resource.reviewed_at = timezone.now()
        resource.save(update_fields=["status", "published_at", "reviewed_by", "reviewed_at"])

        teacher_delete = self.client.delete(
            f"{STUDIO}resources/{resource.pk}/assets/{asset.pk}/"
        )
        self.assertEqual(teacher_delete.status_code, 409)
        self.assertTrue(stored.exists())

        self.client.force_authenticate(self.admin)
        archived = self.client.post(f"{STUDIO}resources/{resource.pk}/archive/", {}, format="json")
        self.assertEqual(archived.status_code, 200, archived.content)
        self.assertEqual(archived.json()["status"], "archived")
        deleted = self.client.delete(f"{STUDIO}resources/{resource.pk}/assets/{asset.pk}/")
        self.assertEqual(deleted.status_code, 204)
        self.assertFalse(stored.exists())
