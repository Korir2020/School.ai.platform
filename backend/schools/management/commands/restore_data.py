"""Restore a Marian snapshot created by backup_data or the platform Backups page.

    python manage.py restore_data marian-backup-20261104-1200.json.gz            # check only
    python manage.py restore_data FILE --yes                                      # restore into an empty database
    python manage.py restore_data FILE --yes --replace                            # wipe this database first

The file is checked (format, checksum, record types, migration state) before
anything changes. The restore runs in one transaction: it either fully
succeeds or leaves the database as it was. New snapshots omit fee records and
some user-authored message text; a restore cannot recover those omissions.
"""
import json
import os
import tempfile

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from api.backup import read_backup


class Command(BaseCommand):
    help = "Check and restore a Marian backup file."

    def add_arguments(self, parser):
        parser.add_argument("file")
        parser.add_argument("--yes", action="store_true", help="Actually restore (without it, only checks the file).")
        parser.add_argument("--replace", action="store_true", help="Delete all current data first.")
        parser.add_argument("--ignore-version", action="store_true", help="Restore even if migration state differs.")

    def handle(self, *args, **opts):
        with open(opts["file"], "rb") as fh:
            doc, report = read_backup(fh.read())
        meta = report["meta"] or {}
        for p in report["problems"]:
            self.stderr.write(self.style.ERROR("Problem: " + p))
        for w in report["warnings"]:
            self.stderr.write(self.style.WARNING("Warning: " + w))
        if not report["ok"]:
            raise CommandError("The backup failed its checks. Nothing was changed.")
        self.stdout.write(f"Backup from {meta.get('created_at')}: checksum OK.")
        if meta.get("redactions"):
            self.stderr.write(self.style.WARNING(
                "This privacy-redacted snapshot omits fee records and user-authored message text. "
                "A --replace restore will not restore those records."
            ))
        if not opts["yes"]:
            self.stdout.write("Check only. Run again with --yes to restore.")
            return
        if report["warnings"] and not opts["ignore_version"]:
            raise CommandError("Migration state differs. Use a server at the backup's version, or pass --ignore-version.")
        has_data = get_user_model().objects.exists()
        if has_data and not opts["replace"]:
            raise CommandError("This database already has data. Pass --replace to wipe it first.")
        fd, tmp = tempfile.mkstemp(suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(doc["objects"], fh)
            with transaction.atomic():
                if opts["replace"]:
                    call_command("flush", interactive=False, verbosity=0)
                call_command("loaddata", tmp, verbosity=0)
        finally:
            os.remove(tmp)
        self.stdout.write(self.style.SUCCESS("Restore completed."))
