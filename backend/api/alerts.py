"""Alert delivery shared by in-app notifications and school announcements.

- In-app alerts are always created.
- Email and SMS respect each person's NotificationPreference (default on).
- Slow work (email, SMS) runs after the response in a background thread, or
  inline when MESSAGING_SYNC is true (tests and the retry command).
"""
import logging
import sys
import threading

from django.conf import settings
from django.core.mail import EmailMessage, get_connection
from django.db import close_old_connections, transaction
from django.utils import timezone

from schools.models import (
    AnnouncementRecipient,
    Enrollment,
    GuardianProfile,
    Notification,
    NotificationPreference,
    SchoolAdminProfile,
    StaffProfile,
    StudentGuardian,
    TeacherProfile,
)

from . import sms

log = logging.getLogger(__name__)
EMAIL_BATCH = 50  # recipients per email, sent as Bcc so addresses stay private


def sync_mode():
    return getattr(settings, "MESSAGING_SYNC", "test" in sys.argv)


def run_later(fn, *args):
    """Run fn after the current transaction commits, off the request thread."""
    def go():
        try:
            fn(*args)
        except Exception:
            log.exception("Background alert delivery failed")
        finally:
            close_old_connections()

    def start():
        if sync_mode():
            fn(*args)
        else:
            threading.Thread(target=go, daemon=True).start()

    if sync_mode():
        fn(*args)
    else:
        transaction.on_commit(start)


def prefs_for(users):
    """{user_id: (email_on, sms_on)} with defaults for people who never chose."""
    rows = NotificationPreference.objects.filter(user__in=users).values_list("user_id", "email_alerts", "sms_alerts")
    got = {u: (e, s) for u, e, s in rows}
    return {u.id: got.get(u.id, (True, True)) for u in users}


def email_configured():
    backend = getattr(settings, "EMAIL_BACKEND", "")
    if "console" in backend or "locmem" in backend or "BrevoEmailBackend" in backend:
        return True
    return bool(getattr(settings, "EMAIL_HOST", ""))


def send_bulk_email(addresses, subject, body, reply_to=None):
    """Send one email to many addresses using Bcc batches. Returns (sent_set, failed_set)."""
    addresses = [a for a in dict.fromkeys(addresses) if a]
    sent, failed = set(), set()
    if not addresses:
        return sent, failed
    conn = get_connection(fail_silently=False)
    for i in range(0, len(addresses), EMAIL_BATCH):
        chunk = addresses[i:i + EMAIL_BATCH]
        msg = EmailMessage(subject=subject[:200], body=body, from_email=settings.DEFAULT_FROM_EMAIL,
                           to=[settings.DEFAULT_FROM_EMAIL] if len(chunk) > 1 else chunk,
                           bcc=chunk if len(chunk) > 1 else None,
                           reply_to=[reply_to] if reply_to else None, connection=conn)
        try:
            msg.send()
            sent.update(chunk)
        except Exception as exc:
            log.warning("Alert email batch failed: %s", type(exc).__name__)
            failed.update(chunk)
    return sent, failed


FOOTER = ("\n\n--\nSent by {school} through Marian.\n"
          "To stop email alerts, sign in to Marian and turn them off under Home > Alert settings.")


# ---- in-app notification -> email copy ---------------------------------

def email_copy_of_notifications(school_name, user_ids, message):
    from django.contrib.auth import get_user_model
    users = list(get_user_model().objects.filter(id__in=user_ids, is_active=True).exclude(email=""))
    p = prefs_for(users)
    to = [u.email for u in users if p[u.id][0]]
    if to:
        send_bulk_email(to, f"Marian: {message[:80]}", message + FOOTER.format(school=school_name))


def notify(school, users, kind, message, join_request=None, email=True):
    users = [u for u in users if u is not None]
    Notification.objects.bulk_create([
        Notification(school=school, recipient=u, kind=kind, message=message[:255], join_request=join_request)
        for u in users])
    if email and users:
        run_later(email_copy_of_notifications, school.name, [u.id for u in users], message)


# ---- audiences --------------------------------------------------------

def _parents(school_id, class_level_id=None, stream_id=None):
    enr = Enrollment.objects.filter(is_active=True, student__school_id=school_id, student__status="active")
    if class_level_id:
        enr = enr.filter(class_level_id=class_level_id)
    if stream_id:
        enr = enr.filter(stream_id=stream_id)
    links = StudentGuardian.objects.filter(student_id__in=enr.values("student_id")).values("guardian_id")
    return GuardianProfile.objects.filter(school_id=school_id, id__in=links, user__is_active=True).select_related("user")


def audience_people(school_id, audience, class_level_id=None, stream_id=None):
    """Return {user_id: (user, role, phone)} for an announcement audience."""
    out = {}

    def add(user, role, phone=""):
        if user.is_active and user.id not in out:
            out[user.id] = (user, role, phone or "")

    scoped = bool(class_level_id or stream_id)
    if audience in ("everyone", "staff", "admins") and not scoped:
        for p in SchoolAdminProfile.objects.filter(school_id=school_id).select_related("user"):
            add(p.user, "admin")
    if audience in ("everyone", "staff", "teachers") and not scoped:
        for p in TeacherProfile.objects.filter(school_id=school_id).select_related("user"):
            add(p.user, "teacher", p.phone)
    if audience in ("everyone", "staff") and not scoped:
        for p in StaffProfile.objects.filter(school_id=school_id).select_related("user"):
            add(p.user, "staff")
    if audience in ("everyone", "parents"):
        for g in _parents(school_id, class_level_id, stream_id):
            add(g.user, "parent", g.phone)
    return out


# ---- announcement delivery -------------------------------------------

def deliver_announcement(announcement_id):
    from schools.models import Announcement
    a = Announcement.objects.select_related("school").get(pk=announcement_id)
    rows = list(a.recipients.select_related("user"))
    school = a.school

    if a.send_email:
        queued = [r for r in rows if r.email_status == "queued"]
        by_addr = {}
        for r in queued:
            by_addr.setdefault(r.user.email.strip().lower(), []).append(r)
        subject = ("URGENT: " if a.priority == "urgent" else "") + f"{school.name}: {a.title}"
        body = f"{a.title}\n\n{a.body}" + FOOTER.format(school=school.name)
        sent, failed = send_bulk_email(list(by_addr), subject, body, reply_to=school.email or None)
        for addr, rs in by_addr.items():
            for r in rs:
                r.email_status = "sent" if addr in sent else "failed"
        AnnouncementRecipient.objects.bulk_update(queued, ["email_status"])

    if a.send_sms:
        queued = [r for r in rows if r.sms_status == "queued"]
        text = a.sms_text or f"{school.name}: {a.title}. {a.body}"
        result = sms.send_bulk([r.sms_phone for r in queued], text)
        for r in queued:
            status, detail = result.get(r.sms_phone, ("failed", "No response."))
            r.sms_status = status
            if status != "sent":
                r.error = (detail or "")[:200]
        AnnouncementRecipient.objects.bulk_update(queued, ["sms_status", "error"])

    finish_status(a)


def finish_status(a):
    rows = a.recipients
    bad = rows.filter(email_status="failed").exists() or rows.filter(sms_status__in=["failed", "not_configured"]).exists()
    still = rows.filter(email_status="queued").exists() or rows.filter(sms_status="queued").exists()
    a.status = "sending" if still else ("partial" if bad else "sent")
    if not a.sent_at:
        a.sent_at = timezone.now()
    a.save(update_fields=["status", "sent_at"])
