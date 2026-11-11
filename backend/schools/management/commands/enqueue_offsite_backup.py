from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from api.offsite_backup import configured
from schools.models import OffsiteBackupRun


class Command(BaseCommand):
    help = "Queue one scheduled full off-site backup if the interval has elapsed."

    def add_arguments(self, parser):
        parser.add_argument("--minimum-interval-hours", type=int, default=23,
                            help="Avoid duplicate scheduled runs inside this interval (default: 23 hours).")

    def handle(self, *args, **options):
        if not configured():
            raise CommandError("Off-site backups are disabled; configure the private object store and encryption keys first.")
        interval = max(1, min(8760, options["minimum_interval_hours"]))
        now = timezone.now()
        cutoff = now - timedelta(hours=interval)
        with transaction.atomic():
            active = OffsiteBackupRun.objects.select_for_update().filter(
                requested_by__isnull=True, status__in=["queued", "running"],
            ).first()
            if active:
                self.stdout.write(f"Scheduled backup already queued or running: {active.id}")
                return
            recent = OffsiteBackupRun.objects.filter(
                requested_by__isnull=True, status="succeeded", finished_at__gte=cutoff,
            ).first()
            if recent:
                self.stdout.write(f"Recent scheduled backup already succeeded: {recent.id}")
                return
            run = OffsiteBackupRun.objects.create()
        self.stdout.write(self.style.SUCCESS(f"Scheduled off-site backup queued: {run.id}"))
