import time

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from api.background_jobs import cleanup_expired_artifacts, process_one_job


class Command(BaseCommand):
    help = "Run the durable background document-job worker."

    def add_arguments(self, parser):
        parser.add_argument("--poll-interval", type=float, default=2.0)
        parser.add_argument(
            "--once", action="store_true",
            help="Process at most one queued job, then exit.",
        )

    def handle(self, *args, **options):
        interval = options["poll_interval"]
        if interval <= 0 or interval > 60:
            raise CommandError("--poll-interval must be greater than 0 and at most 60 seconds.")
        if options["once"]:
            processed = process_one_job()
            self.stdout.write("Processed one job." if processed else "No jobs queued.")
            cleanup_expired_artifacts()
            return

        self.stdout.write(self.style.SUCCESS("Background document worker started."))
        next_cleanup = 0
        while True:
            now = time.monotonic()
            if now >= next_cleanup:
                cleanup_expired_artifacts()
                next_cleanup = now + 900
            if not process_one_job():
                time.sleep(interval)
