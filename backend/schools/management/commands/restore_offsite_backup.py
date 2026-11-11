import getpass
import json
import os
import sqlite3
import shutil
import subprocess
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connections

from api.offsite_backup import download_and_decrypt


def _pg_env(db):
    env = os.environ.copy()
    if db.get("PASSWORD"):
        env["PGPASSWORD"] = str(db["PASSWORD"])
    env.setdefault("PGSSLMODE", os.environ.get("PGSSLMODE", "prefer"))
    return env


def _check_empty_postgres(dbname):
    import psycopg
    source = settings.DATABASES["default"]
    if str(dbname) == str(source.get("NAME")):
        raise CommandError("Restore target must be a different, newly created database.")
    conn = psycopg.connect(dbname=dbname, user=source.get("USER") or None,
                           password=source.get("PASSWORD") or None,
                           host=source.get("HOST") or None, port=source.get("PORT") or None,
                           connect_timeout=10)
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                           "WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname <> 'information_schema' "
                           "AND c.relkind IN ('r','p','v','m','S','f')")
            if cursor.fetchone()[0]:
                raise CommandError("PostgreSQL restore target is not empty; restore was refused.")
    finally:
        conn.close()


def _validate_media_tar(path, temp_parent):
    root = Path(temp_parent, "media-staging")
    root.mkdir()
    with tarfile.open(path, "r:gz") as archive:
        members = archive.getmembers()
        for member in members:
            name = PurePosixPath(member.name)
            if (name.is_absolute() or ".." in name.parts or member.issym() or member.islnk()
                    or not (member.isdir() or member.isfile())):
                raise CommandError("Media archive contains an unsafe path or link.")
        for member in members:
            parts = PurePosixPath(member.name).parts
            if not parts or parts[0] != "media":
                raise CommandError("Media archive layout is invalid.")
        # Extract only after all members have passed path/link checks. Write
        # regular files ourselves for compatibility with older Python tarfile.
        for member in members:
            destination = root.joinpath(*PurePosixPath(member.name).parts)
            if member.isdir():
                destination.mkdir(parents=True, exist_ok=True)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    raise CommandError("Media archive contains an unreadable file.")
                with source, destination.open("xb") as output:
                    shutil.copyfileobj(source, output, 1024 * 1024)
    extracted = root / "media"
    if not extracted.exists():
        extracted.mkdir()
    return extracted


def _verify_sqlite_database(path):
    db = sqlite3.connect(f"file:{Path(path).resolve()}?mode=ro", uri=True)
    try:
        result = db.execute("PRAGMA integrity_check").fetchone()
        if not result or result[0] != "ok":
            raise CommandError("Restored SQLite database failed PRAGMA integrity_check.")
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "django_migrations" not in tables or "schools_school" not in tables:
            raise CommandError("Restored SQLite file is missing required Marian application tables.")
    finally:
        db.close()


def _verify_postgres_database(dbname):
    import psycopg
    source = settings.DATABASES["default"]
    with psycopg.connect(dbname=dbname, user=source.get("USER") or None,
                         password=source.get("PASSWORD") or None,
                         host=source.get("HOST") or None, port=source.get("PORT") or None,
                         connect_timeout=10) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT to_regclass('public.django_migrations'), to_regclass('public.schools_school')")
            tables = cursor.fetchone()
            if not all(tables):
                raise CommandError("Restored PostgreSQL target is missing required Marian application tables.")
            cursor.execute("SELECT count(*) FROM public.django_migrations")
            if cursor.fetchone()[0] < 1:
                raise CommandError("Restored PostgreSQL database has no migration history.")


def _append_restore_audit(path, action, run_id, target, media_target, manifest, error=""):
    record = {
        "at": datetime.now(timezone.utc).isoformat(), "action": action,
        "operator": getpass.getuser(), "run_id": str(run_id),
        "database_target": str(target), "media_staging_target": str(media_target),
        "database_engine": manifest.get("database_engine"),
        "manifest_run_id": manifest.get("run_id"), "error": error[:1000],
    }
    audit_path = Path(path).expanduser().resolve()
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(audit_path, flags, 0o600)
    os.fchmod(descriptor, 0o600)
    with os.fdopen(descriptor, "a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


class Command(BaseCommand):
    help = "Restore an off-site set only into a new empty database and a new media staging folder."

    def add_arguments(self, parser):
        parser.add_argument("run_id", help="Succeeded off-site backup UUID")
        parser.add_argument("--target-database", required=True,
                            help="New SQLite file path, or the name of a pre-created empty PostgreSQL database.")
        parser.add_argument("--media-staging-dir", required=True,
                            help="Path for a newly-created restored media staging directory.")
        parser.add_argument("--yes", action="store_true", help="Perform restore; otherwise only verify and report targets.")
        parser.add_argument("--audit-log", default=os.environ.get("BACKUP_RESTORE_AUDIT_LOG", ""),
                            help="Protected append-only JSONL audit log (required with --yes).")

    def handle(self, *args, **opts):
        source_engine = settings.DATABASES["default"]["ENGINE"]
        target = Path(opts["target_database"]).expanduser().resolve()
        media_target = Path(opts["media_staging_dir"]).expanduser().resolve()
        live_media = Path(settings.MEDIA_ROOT).expanduser().resolve()
        if source_engine.endswith("sqlite3") and target.exists():
            raise CommandError("SQLite restore target already exists; refusing to overwrite.")
        if source_engine.endswith("sqlite3"):
            live_db = Path(settings.DATABASES["default"]["NAME"]).expanduser().resolve()
            if target == live_db:
                raise CommandError("Restore target must not be the configured live SQLite database.")
        if media_target.exists():
            raise CommandError("Media staging directory already exists; refusing to overwrite.")
        if (media_target == live_media or media_target.is_relative_to(live_media)
                or live_media.is_relative_to(media_target)):
            raise CommandError("Media staging directory must be separate from configured MEDIA_ROOT.")
        if source_engine.endswith("sqlite3"):
            target.parent.mkdir(parents=True, exist_ok=True)
        elif not source_engine.endswith("postgresql"):
            raise CommandError("Unsupported configured database engine.")
        elif not opts["yes"]:
            # The PostgreSQL target's emptiness is checked for both verify and restore modes below.
            _check_empty_postgres(opts["target_database"])
        elif opts["yes"]:
            _check_empty_postgres(opts["target_database"])

        with tempfile.TemporaryDirectory(prefix="marian-restore-") as folder:
            try:
                _, manifest, files = download_and_decrypt(opts["run_id"], folder)
            except Exception as exc:
                raise CommandError(f"Backup verification/download failed: {exc}") from exc
            engine = manifest.get("database_engine")
            if source_engine.endswith("sqlite3") and engine != "sqlite":
                raise CommandError("Backup database type does not match the configured SQLite target.")
            if source_engine.endswith("postgresql") and engine != "postgresql-custom":
                raise CommandError("Backup database type does not match the configured PostgreSQL target.")
            staged_media = _validate_media_tar(files["media"], folder)
            self.stdout.write(f"Verified backup {opts['run_id']}; database and media checksums are valid.")
            if not opts["yes"]:
                self.stdout.write("Check only. No data restored. Review targets, then rerun with --yes.")
                return
            if not opts["audit_log"]:
                raise CommandError("Actual restore requires --audit-log or BACKUP_RESTORE_AUDIT_LOG.")
            _append_restore_audit(opts["audit_log"], "restore_started", opts["run_id"],
                                  target, media_target, manifest)
            sqlite_target_created = False
            media_target_created = False
            try:
                if source_engine.endswith("sqlite3"):
                    source_path = Path(files["database"])
                    try:
                        with source_path.open("rb") as src, target.open("xb") as dst:
                            sqlite_target_created = True
                            shutil.copyfileobj(src, dst, 1024 * 1024)
                    except FileExistsError as exc:
                        raise CommandError("SQLite restore target was created concurrently; refusing overwrite.") from exc
                    _verify_sqlite_database(target)
                else:
                    db = settings.DATABASES["default"]
                    subprocess.run([os.environ.get("PG_RESTORE_BIN", "pg_restore"), "--list", files["database"]],
                                   check=True, env=_pg_env(db), capture_output=True, text=True, timeout=600)
                    cmd = [os.environ.get("PG_RESTORE_BIN", "pg_restore"), "--exit-on-error", "--no-owner",
                           "--no-privileges", "--dbname", str(opts["target_database"]), files["database"]]
                    subprocess.run(cmd, check=True, env=_pg_env(db), capture_output=True,
                                   text=True, timeout=7200)
                    _verify_postgres_database(opts["target_database"])
                # mkdir is exclusive: a concurrent directory is never replaced.
                media_target.mkdir(parents=True, exist_ok=False)
                media_target_created = True
                for child in staged_media.iterdir():
                    shutil.move(str(child), str(media_target / child.name))
                _append_restore_audit(opts["audit_log"], "restore_completed", opts["run_id"],
                                      target, media_target, manifest)
            except Exception as exc:
                if sqlite_target_created:
                    target.unlink(missing_ok=True)
                if media_target_created:
                    shutil.rmtree(media_target, ignore_errors=True)
                _append_restore_audit(opts["audit_log"], "restore_failed", opts["run_id"],
                                      target, media_target, manifest, str(exc))
                raise
        self.stdout.write(self.style.SUCCESS(
            f"Restored to new database target {target} and staging media folder {media_target}. "
            "No existing application database or MEDIA_ROOT was changed."))
