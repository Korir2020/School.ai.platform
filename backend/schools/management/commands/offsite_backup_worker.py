import time
from django.core.management.base import BaseCommand, CommandError
from api.offsite_backup import claim_next_run, configured, process_run


class Command(BaseCommand):
    help = "Process queued encrypted off-site backups (schedule this command externally)."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Process at most one queued run.")
        parser.add_argument("--poll-seconds", type=int, default=15)

    def handle(self, *args, **options):
        if not configured():
            raise CommandError("Off-site backups are disabled: configure the S3 bucket/credentials, AES key and manifest HMAC key.")
        while True:
            claimed = claim_next_run()
            if claimed is None:
                if options["once"]:
                    self.stdout.write("No queued backup run.")
                    return
                time.sleep(max(1, min(300, options["poll_seconds"])))
                continue
            run_id, lease_token = claimed
            outcome = process_run(run_id, lease_token)
            if outcome == "succeeded":
                styled = self.style.SUCCESS(f"Backup {run_id}: succeeded")
            elif outcome == "queued":
                styled = self.style.WARNING(f"Backup {run_id}: temporarily failed; automatically requeued")
            elif outcome == "failed":
                styled = self.style.ERROR(f"Backup {run_id}: failed after all retries")
            else:
                styled = self.style.WARNING(f"Backup {run_id}: lease was lost; check run status")
            self.stdout.write(styled)
            if options["once"]:
                return
