"""Finish any announcement deliveries still queued (for example after a restart).

    python manage.py process_announcements
"""
from django.core.management.base import BaseCommand
from django.db.models import Q

from api.alerts import deliver_announcement
from schools.models import Announcement


class Command(BaseCommand):
    help = "Send queued announcement emails and SMS."

    def handle(self, *args, **opts):
        ids = list(Announcement.objects.filter(
            Q(recipients__email_status="queued") | Q(recipients__sms_status="queued")).values_list("id", flat=True).distinct())
        for pk in ids:
            deliver_announcement(pk)
        self.stdout.write(self.style.SUCCESS(f"Processed {len(ids)} announcement(s)."))
