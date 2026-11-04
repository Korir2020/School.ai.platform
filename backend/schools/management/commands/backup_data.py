"""Write a full, checksummed Marian backup to disk.

    python manage.py backup_data --output-dir /var/backups/marian --keep 14

Run it on a schedule (cron, Render cron job or the GitHub workflow). Keep
copies off the server: a backup on the same disk dies with the disk.
"""
import os

from django.core.management.base import BaseCommand
from django.utils import timezone

from api.backup import build_full_backup
from schools.models import MarkAuditLog


class Command(BaseCommand):
    help = "Create a full backup file (gzip JSON with checksum)."

    def add_arguments(self, parser):
        parser.add_argument("--output-dir", default="backups")
        parser.add_argument("--keep", type=int, default=14, help="How many recent backups to keep (0 = keep all).")

    def handle(self, *args, **opts):
        out = opts["output_dir"]
        os.makedirs(out, exist_ok=True)
        blob, meta = build_full_backup()
        name = "marian-backup-" + timezone.now().strftime("%Y%m%d-%H%M%S") + ".json.gz"
        path = os.path.join(out, name)
        with open(path, "wb") as fh:
            fh.write(blob)
        MarkAuditLog.objects.create(action="backup_created", details={"file": name, "records": meta["total"], "sha256": meta["sha256"]})
        self.stdout.write(self.style.SUCCESS(f"Backup written: {path} ({meta['total']} records, sha256 {meta['sha256'][:12]}...)"))
        if opts["keep"] > 0:
            old = sorted(f for f in os.listdir(out) if f.startswith("marian-backup-") and f.endswith(".json.gz"))
            for f in old[:-opts["keep"]]:
                os.remove(os.path.join(out, f))
                self.stdout.write(f"Removed old backup {f}")
