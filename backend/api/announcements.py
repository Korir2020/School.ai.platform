"""School announcements: one message to an audience by in-app alert, email and SMS.

Only school administrators (including deputies) create and send.
Everyone else sees only announcements they received.
"""
import os
import sys

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle

from schools.models import (
    Announcement,
    AnnouncementRecipient,
    ClassLevel,
    GuardianProfile,
    MarkAuditLog,
    Notification,
    NotificationPreference,
    SchoolAdminProfile,
    StaffProfile,
    Stream,
    TeacherProfile,
)

from . import alerts, sms
from .suspension import SchoolNotSuspended

PERMS = [IsAuthenticated, SchoolNotSuspended]
AUDIENCES = dict(Announcement.AUDIENCES)


def sms_limit():
    try:
        return max(0, int(os.environ.get("DJANGO_SMS_MAX_PER_ANNOUNCEMENT", "2000")))
    except ValueError:
        return 2000


class AnnouncementThrottle(SimpleRateThrottle):
    scope = "announcement_send"
    rate = "1000/min" if "test" in sys.argv else "20/hour"

    def get_cache_key(self, request, view):
        if request.method != "POST" or not request.user.is_authenticated:
            return None
        return self.cache_format % {"scope": self.scope, "ident": request.user.pk}


def _admin(user):
    return SchoolAdminProfile.objects.filter(user=user).first()


def _err(msg, status=400):
    return Response({"detail": msg}, status=status)


def _clean(data, school_id):
    """Validate input. Returns (fields, error)."""
    title = str(data.get("title") or "").strip()
    body = str(data.get("body") or "").strip()
    audience = str(data.get("audience") or "everyone")
    if not 3 <= len(title) <= 120:
        return None, "Give the announcement a title of 3 to 120 characters."
    if not 1 <= len(body) <= 2000:
        return None, "Write a message of up to 2000 characters."
    if audience not in AUDIENCES:
        return None, "Choose who should receive this announcement."
    level = stream = None
    if data.get("stream"):
        stream = Stream.objects.filter(pk=data.get("stream"), school_id=school_id).select_related("class_level").first()
        if not stream:
            return None, "That stream is not in your school."
        level = stream.class_level
    elif data.get("class_level"):
        if not Stream.objects.filter(school_id=school_id, class_level_id=data.get("class_level")).exists():
            return None, "That class is not in your school."
        level = ClassLevel.objects.filter(pk=data.get("class_level")).first()
    if (level or stream) and audience != "parents":
        return None, "A class or stream can only be chosen when sending to parents."
    sms_text = " ".join(str(data.get("sms_text") or "").split())
    if len(sms_text) > sms.MAX_LEN:
        return None, f"The SMS text must be {sms.MAX_LEN} characters or fewer."
    flag = lambda k: data.get(k) in (True, "true", "1", 1, "yes")
    return {
        "title": title, "body": body, "audience": audience,
        "class_level": level, "stream": stream,
        "priority": "urgent" if data.get("priority") == "urgent" else "normal",
        "send_email": flag("send_email"), "send_sms": flag("send_sms"), "sms_text": sms_text,
    }, None


def _plan(school_id, f):
    """Work out who gets what, without sending anything."""
    people = alerts.audience_people(school_id, f["audience"],
                                    f["class_level"].id if f["class_level"] else None,
                                    f["stream"].id if f["stream"] else None)
    users = [u for u, _, _ in people.values()]
    prefs = alerts.prefs_for(users)
    email_ok, sms_ok = alerts.email_configured(), sms.is_configured()
    limit, sms_used, plan = sms_limit(), 0, []
    for uid, (user, role, phone) in people.items():
        e_on, s_on = prefs[uid]
        es = ss = ""
        num = ""
        if f["send_email"]:
            es = ("not_configured" if not email_ok else "no_contact" if not user.email.strip()
                  else "opted_out" if not e_on else "queued")
        if f["send_sms"]:
            num = sms.normalize_phone(phone)
            ss = ("not_configured" if not sms_ok else "no_contact" if not num
                  else "opted_out" if not s_on else "queued")
            if ss == "queued":
                sms_used += 1
                if sms_used > limit:
                    ss = "over_limit"
        plan.append((user, role, es, ss, num))
    return plan


def _summary(plan):
    count = lambda i, v: sum(1 for p in plan if p[i] == v)
    return {
        "recipients": len(plan),
        "by_role": {r: sum(1 for p in plan if p[1] == r) for r in ("admin", "teacher", "staff", "parent") if any(p[1] == r for p in plan)},
        "email": {"will_send": count(2, "queued"), "no_email": count(2, "no_contact"), "opted_out": count(2, "opted_out")},
        "sms": {"will_send": count(3, "queued"), "no_phone": count(3, "no_contact"), "opted_out": count(3, "opted_out"),
                "over_limit": count(3, "over_limit")},
    }


def _status_view():
    return {"email_ready": alerts.email_configured(), "sms_ready": sms.is_configured(),
            "sms_provider": sms.provider() or None, "sms_max_length": sms.MAX_LEN,
            "sms_limit": sms_limit()}


def _row(a, mine=None, stats=None):
    d = {
        "id": a.id, "title": a.title, "body": a.body, "priority": a.priority,
        "audience": a.audience, "audience_label": _audience_label(a),
        "created_at": a.created_at, "sent_at": a.sent_at,
        "author": (a.created_by.get_full_name() or a.created_by.username) if a.created_by else None,
    }
    if mine is not None:
        d["read"] = mine.read_at is not None
    if stats is not None:
        d.update({"status": a.status, "send_email": a.send_email, "send_sms": a.send_sms,
                  "sms_text": a.sms_text, "class_level": a.class_level_id, "stream": a.stream_id, **stats})
    return d


def _audience_label(a):
    label = AUDIENCES.get(a.audience, a.audience)
    if a.stream:
        return f"Parents of {a.stream}"
    if a.class_level:
        return f"Parents of {a.class_level.name}"
    return label


def _stats(a):
    q = a.recipients.aggregate(
        total=Count("id"), read=Count("id", filter=Q(read_at__isnull=False)),
        email_sent=Count("id", filter=Q(email_status="sent")), email_failed=Count("id", filter=Q(email_status="failed")),
        email_queued=Count("id", filter=Q(email_status="queued")),
        sms_sent=Count("id", filter=Q(sms_status="sent")), sms_failed=Count("id", filter=Q(sms_status__in=["failed", "not_configured"])),
        sms_queued=Count("id", filter=Q(sms_status="queued")),
        skipped=Count("id", filter=Q(email_status__in=["no_contact", "opted_out"]) | Q(sms_status__in=["no_contact", "opted_out", "over_limit"])),
    )
    return q


def _send(a, plan, user):
    AnnouncementRecipient.objects.bulk_create([
        AnnouncementRecipient(announcement=a, user=u, role=role, email_status=es, sms_status=ss, sms_phone=num)
        for u, role, es, ss, num in plan])
    Notification.objects.bulk_create([
        Notification(school_id=a.school_id, recipient=u, kind="announcement",
                     message=(("Urgent: " if a.priority == "urgent" else "Announcement: ") + a.title)[:255])
        for u, *_ in plan if u.id != user.id])
    a.status = "sending"
    a.sent_at = timezone.now()
    a.save(update_fields=["status", "sent_at"])
    MarkAuditLog.objects.create(school_id=a.school_id, user=user, action="announcement_sent", details={
        "announcement": a.id, "title": a.title, "audience": a.audience, "recipients": len(plan),
        "email": a.send_email, "sms": a.send_sms})
    alerts.run_later(alerts.deliver_announcement, a.id)


@api_view(["GET", "POST"])
@permission_classes(PERMS)
@throttle_classes([AnnouncementThrottle])
def announcements(request):
    boss = _admin(request.user)
    if request.method == "POST":
        if not boss:
            return _err("Only school administrators can send announcements.", 403)
        f, e = _clean(request.data, boss.school_id)
        if e:
            return _err(e)
        draft = request.data.get("draft") in (True, "true", "1")
        plan = _plan(boss.school_id, f)
        if not draft and not plan:
            return _err("Nobody is in that audience yet.")
        with transaction.atomic():
            a = Announcement.objects.create(school_id=boss.school_id, created_by=request.user, **f)
            if not draft:
                _send(a, plan, request.user)
        a.refresh_from_db()
        return Response(_row(a, stats=_stats(a)), status=201)

    if boss:
        rows = Announcement.objects.filter(school_id=boss.school_id).select_related("created_by", "class_level", "stream")[:100]
        return Response({"is_admin": True, "channels": _status_view(),
                         "results": [_row(a, stats=_stats(a)) for a in rows]})
    mine = (AnnouncementRecipient.objects.filter(user=request.user)
            .select_related("announcement__created_by", "announcement__class_level", "announcement__stream")
            .order_by("-announcement__sent_at", "-id")[:100])
    return Response({"is_admin": False, "unread": sum(1 for r in mine if r.read_at is None),
                     "results": [_row(r.announcement, mine=r) for r in mine]})


@api_view(["POST"])
@permission_classes(PERMS)
def announcement_preview(request):
    boss = _admin(request.user)
    if not boss:
        return _err("Only school administrators can send announcements.", 403)
    data = {"title": "preview", "body": "preview"}
    data.update({k: request.data.get(k) for k in request.data if k not in ("title", "body")})
    f, e = _clean(data, boss.school_id)
    if e:
        return _err(e)
    return Response({**_summary(_plan(boss.school_id, f)), "channels": _status_view()})


def _own(request, pk):
    boss = _admin(request.user)
    if not boss:
        return None, _err("Only school administrators can do this.", 403)
    a = Announcement.objects.filter(pk=pk, school_id=boss.school_id).first()
    if not a:
        return None, _err("Not found.", 404)
    return a, None


@api_view(["GET", "PATCH", "DELETE"])
@permission_classes(PERMS)
def announcement_detail(request, pk):
    if request.method == "GET" and not _admin(request.user):
        r = AnnouncementRecipient.objects.filter(announcement_id=pk, user=request.user).select_related("announcement").first()
        if not r:
            return _err("Not found.", 404)
        return Response(_row(r.announcement, mine=r))
    a, e = _own(request, pk)
    if e:
        return e
    if request.method == "GET":
        problems = [{"name": r.user.get_full_name() or r.user.username, "role": r.role,
                     "email": r.email_status, "sms": r.sms_status, "error": r.error}
                    for r in a.recipients.select_related("user").filter(
                        Q(email_status__in=["failed", "no_contact"]) | Q(sms_status__in=["failed", "no_contact", "over_limit", "not_configured"]))[:200]]
        return Response({**_row(a, stats=_stats(a)), "problems": problems})
    if a.status != "draft":
        return _err("Sent announcements cannot be changed.", 409)
    if request.method == "DELETE":
        a.delete()
        return Response(status=204)
    f, err = _clean({**{k: getattr(a, k) for k in ("title", "body", "audience", "priority", "send_email", "send_sms", "sms_text")},
                     "class_level": a.class_level_id, "stream": a.stream_id, **request.data}, a.school_id)
    if err:
        return _err(err)
    for k, v in f.items():
        setattr(a, k, v)
    a.save()
    return Response(_row(a, stats=_stats(a)))


@api_view(["POST"])
@permission_classes(PERMS)
@throttle_classes([AnnouncementThrottle])
def announcement_send(request, pk):
    a, e = _own(request, pk)
    if e:
        return e
    if a.status != "draft":
        return _err("This announcement was already sent.", 409)
    f = {"audience": a.audience, "class_level": a.class_level, "stream": a.stream,
         "send_email": a.send_email, "send_sms": a.send_sms}
    plan = _plan(a.school_id, f)
    if not plan:
        return _err("Nobody is in that audience yet.")
    with transaction.atomic():
        _send(a, plan, request.user)
    a.refresh_from_db()
    return Response(_row(a, stats=_stats(a)))


@api_view(["POST"])
@permission_classes(PERMS)
@throttle_classes([AnnouncementThrottle])
def announcement_retry(request, pk):
    """Re-queue failed email and SMS deliveries (for example after the provider is fixed)."""
    a, e = _own(request, pk)
    if e:
        return e
    if a.status == "draft":
        return _err("Send the announcement first.", 409)
    n_e = a.recipients.filter(email_status="failed").update(email_status="queued") if a.send_email else 0
    n_s = 0
    if a.send_sms:
        if not sms.is_configured():
            return _err("SMS is not set up yet, so failed messages cannot be retried.", 409)
        n_s = a.recipients.filter(sms_status__in=["failed", "not_configured"]).exclude(sms_phone="").update(sms_status="queued", error="")
    if not (n_e or n_s):
        return _err("There is nothing to retry.")
    a.status = "sending"
    a.save(update_fields=["status"])
    MarkAuditLog.objects.create(school_id=a.school_id, user=request.user, action="announcement_retry",
                                details={"announcement": a.id, "email": n_e, "sms": n_s})
    alerts.run_later(alerts.deliver_announcement, a.id)
    return Response({"requeued_email": n_e, "requeued_sms": n_s})


@api_view(["POST"])
@permission_classes(PERMS)
def announcement_read(request, pk):
    n = AnnouncementRecipient.objects.filter(announcement_id=pk, user=request.user, read_at__isnull=True).update(read_at=timezone.now())
    if not n and not AnnouncementRecipient.objects.filter(announcement_id=pk, user=request.user).exists():
        return _err("Not found.", 404)
    return Response({"read": True})


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def alert_preferences(request):
    p, _ = NotificationPreference.objects.get_or_create(user=request.user)
    if request.method == "PATCH":
        for k in ("email_alerts", "sms_alerts"):
            if k in request.data:
                v = request.data[k]
                if not isinstance(v, bool):
                    return _err(f"{k} must be true or false.")
                setattr(p, k, v)
        p.save()
    phone = ""
    for model in (TeacherProfile, GuardianProfile):
        prof = model.objects.filter(user=request.user).first()
        if prof:
            phone = prof.phone
    return Response({"email_alerts": p.email_alerts, "sms_alerts": p.sms_alerts,
                     "email": request.user.email, "phone": phone,
                     "phone_valid": bool(sms.normalize_phone(phone))})
