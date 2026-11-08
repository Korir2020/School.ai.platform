import sys

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.db.models import Count, Q
from django.http import HttpResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle

from api.calendar_rules import event_dict
from api.connect_rules import (
    ADMIN,
    PARENT,
    ConnectError,
    can_post,
    check_text,
    display_name,
    ensure_default_channels,
    is_muted,
    membership,
    roles_for,
)
from api.suspension import SchoolNotSuspended
from schools.models import (
    CalendarEvent,
    ConnectAck,
    ConnectAttachment,
    ConnectChannel,
    ConnectMute,
    ConnectPost,
    ConnectRead,
    ConnectReport,
    Enrollment,
    GuardianProfile,
    SchoolAdminProfile,
    StaffProfile,
    StudentGuardian,
    TeacherProfile,
)

User = get_user_model()
PERMS = [IsAuthenticated, SchoolNotSuspended]
MAX_PINNED = 3
PAGE = 30


class ConnectPostThrottle(SimpleRateThrottle):
    scope = "connect_post"
    rate = "1000/min" if "test" in sys.argv else "20/min"

    def get_cache_key(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return None
        return self.cache_format % {"scope": self.scope, "ident": request.user.pk}


def _err(code, message, status):
    return Response({"error": code, "message": message}, status=status)


def _ctx(request):
    sid, role = membership(request.user)
    if sid is None:
        return None, None, _err("no_access", "Connect is for school staff and parents linked to a learner.", 403)
    return sid, role, None


def _int(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _flag(value):
    return value is True or str(value).strip().lower() in ("1", "true", "yes")


def _slow(request):
    if ConnectPostThrottle().allow_request(request, None):
        return None
    return _err("slow_down", "You are posting too fast. Please wait a moment.", 429)


def _channel(sid, pk):
    return ConnectChannel.objects.filter(pk=pk, school_id=sid, is_active=True).first()


def _visible_post(sid, role, pk):
    post = (
        ConnectPost.objects.select_related("channel")
        .filter(pk=pk, channel__school_id=sid, channel__is_active=True)
        .first()
    )
    if post is None or (post.is_hidden and role != ADMIN):
        return None
    return post


def _pinned_count(channel, exclude_id=None):
    qs = ConnectPost.objects.filter(channel=channel, is_pinned=True, is_hidden=False)
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)
    return qs.count()


def _serialize(posts, viewer, role):
    posts = list(posts)
    ids = [p.id for p in posts]
    author_ids = {p.author_id for p in posts if p.author_id}
    users = {u.id: u for u in User.objects.filter(id__in=author_ids)}
    roles = roles_for(author_ids)
    mine = set(ConnectAck.objects.filter(post_id__in=ids, user=viewer).values_list("post_id", flat=True))
    event_ids = {p.event_id for p in posts if p.event_id}
    events = {e.id: e for e in CalendarEvent.objects.filter(id__in=event_ids)}
    ack_counts, report_counts = {}, {}
    if role == ADMIN:
        ack_counts = dict(ConnectAck.objects.filter(post_id__in=ids).values_list("post_id").annotate(n=Count("id")))
        report_counts = dict(
            ConnectReport.objects.filter(post_id__in=ids, resolved=False)
            .values_list("post_id")
            .annotate(n=Count("id"))
        )
    pics = dict(ConnectAvatar.objects.filter(user_id__in={q.author_id for q in posts if q.author_id}).values_list("user_id", "updated_at"))
    atts = {}
    att_rows = ConnectAttachment.objects.filter(post_id__in=ids).only("id", "post_id", "name", "content_type", "size").order_by("id")
    for a in att_rows:
        atts.setdefault(a.post_id, []).append({"id": a.id, "name": a.name, "type": a.content_type, "size": a.size})
    out = []
    for p in posts:
        author = users.get(p.author_id)
        arole = roles.get(p.author_id, PARENT)
        row = {
            "id": p.id,
            "channel_id": p.channel_id,
            "body": p.body,
            "author": display_name(author, arole) if author else "Former member",
            "author_role": arole if author else "member",
            "author_pic": int(pics[p.author_id].timestamp()) if p.author_id in pics else None,
            "mine": p.author_id == viewer.id,
            "is_pinned": p.is_pinned,
            "is_urgent": p.is_urgent,
            "created_at": p.created_at.isoformat(),
            "event": event_dict(events[p.event_id]) if p.event_id in events else None,
            "acknowledged": p.id in mine,
            "can_delete": role == ADMIN or p.author_id == viewer.id,
            "attachments": atts.get(p.id, []),
        }
        if role == ADMIN:
            row["author_id"] = p.author_id
            row["hidden"] = p.is_hidden
            row["ack_count"] = ack_counts.get(p.id, 0)
            row["report_count"] = report_counts.get(p.id, 0)
        out.append(row)
    return out


def _mark_read(user, channel):
    newest = (
        ConnectPost.objects.filter(channel=channel, is_hidden=False)
        .order_by("-id")
        .values_list("id", flat=True)
        .first()
        or 0
    )
    try:
        row, _ = ConnectRead.objects.get_or_create(user=user, channel=channel, defaults={"last_read_id": newest})
    except IntegrityError:
        return
    if row.last_read_id < newest:
        row.last_read_id = newest
        row.save(update_fields=["last_read_id", "updated_at"])


@api_view(["GET"])
@permission_classes(PERMS)
def channels(request):
    sid, role, bad = _ctx(request)
    if bad:
        return bad
    ensure_default_channels(sid)
    muted = is_muted(sid, request.user)
    rows = []
    for c in ConnectChannel.objects.filter(school_id=sid, is_active=True):
        last = ConnectRead.objects.filter(user=request.user, channel=c).values_list("last_read_id", flat=True).first() or 0
        unread = ConnectPost.objects.filter(channel=c, id__gt=last, is_hidden=False).exclude(author=request.user).count()
        rows.append(
            {
                "id": c.id,
                "name": c.name,
                "description": c.description,
                "kind": c.kind,
                "can_post": can_post(c, role) and not muted,
                "unread": unread,
            }
        )
    return Response({"channels": rows, "me": {"role": role, "is_admin": role == ADMIN, "muted": muted}})


@api_view(["GET", "POST"])
@permission_classes(PERMS)
def channel_posts(request, pk):
    sid, role, bad = _ctx(request)
    if bad:
        return bad
    channel = _channel(sid, pk)
    if channel is None:
        return _err("not_found", "Channel not found.", 404)
    if request.method == "POST":
        return _create_post(request, sid, role, channel)
    params = request.query_params
    limit = min(max(_int(params.get("limit"), PAGE), 1), 50)
    before = _int(params.get("before"))
    q = (params.get("q") or "").strip()[:60]
    qs = ConnectPost.objects.filter(channel=channel)
    if role != ADMIN:
        qs = qs.filter(is_hidden=False)
    if q:
        qs = qs.filter(body__icontains=q)
    if before:
        qs = qs.filter(id__lt=before)
    rows = list(qs.order_by("-id")[: limit + 1])
    more = len(rows) > limit
    rows = rows[:limit]
    first_page = not before and not q
    pinned = []
    if first_page:
        pinned_qs = ConnectPost.objects.filter(channel=channel, is_pinned=True, is_hidden=False).order_by("-id")[:MAX_PINNED]
        pinned = _serialize(pinned_qs, request.user, role)
        _mark_read(request.user, channel)
    muted = is_muted(sid, request.user)
    return Response(
        {
            "channel": {"id": channel.id, "name": channel.name, "kind": channel.kind},
            "can_post": can_post(channel, role) and not muted,
            "posts": _serialize(rows, request.user, role),
            "pinned": pinned,
            "has_more": more,
        }
    )


def _create_post(request, sid, role, channel):
    if not can_post(channel, role):
        return _err("forbidden", "Only authorized school staff can post in this channel.", 403)
    if is_muted(sid, request.user):
        return _err("muted", "You have been muted by a school administrator.", 403)
    slow = _slow(request)
    if slow:
        return slow
    files, bad_file = _read_files(request)
    if bad_file is not None:
        return bad_file
    body = request.data.get("body")
    try:
        text = check_text(sid, role, request.user, body if isinstance(body, str) else "") if ((isinstance(body, str) and body.strip()) or not files) else ""
    except ConnectError as exc:
        return _err("post_rejected", str(exc), 400)
    pinned = role == ADMIN and _flag(request.data.get("is_pinned"))
    urgent = role == ADMIN and _flag(request.data.get("is_urgent"))
    event = None
    event_id = request.data.get("event_id")
    if event_id not in (None, ""):
        if role != ADMIN:
            return _err("forbidden", "Only school administrators can attach an event.", 403)
        event = CalendarEvent.objects.filter(pk=_int(event_id, -1), school_id=sid).first()
        if event is None:
            return _err("not_found", "Event not found.", 404)
    if pinned and _pinned_count(channel) >= MAX_PINNED:
        return _err("too_many_pinned", "Three posts are already pinned. Unpin one first.", 400)
    post = ConnectPost.objects.create(
        channel=channel, author=request.user, body=text, is_pinned=pinned, is_urgent=urgent, event=event
    )
    for f in files:
        ConnectAttachment.objects.create(post=post, **f)
    return Response(_serialize([post], request.user, role)[0], status=201)


@api_view(["PATCH", "DELETE"])
@permission_classes(PERMS)
def post_detail(request, pk):
    sid, role, bad = _ctx(request)
    if bad:
        return bad
    post = _visible_post(sid, role, pk)
    if post is None:
        return _err("not_found", "Post not found.", 404)
    if request.method == "DELETE":
        if role != ADMIN and post.author_id != request.user.id:
            return _err("forbidden", "You can only delete your own posts.", 403)
        post.delete()
        return Response(status=204)
    if role != ADMIN:
        return _err("forbidden", "Only a school administrator can change a post.", 403)
    for key in ("is_pinned", "is_urgent"):
        if key in request.data:
            setattr(post, key, _flag(request.data.get(key)))
    if "hidden" in request.data:
        post.is_hidden = _flag(request.data.get("hidden"))
        post.hidden_by = request.user if post.is_hidden else None
    if post.is_hidden:
        post.is_pinned = False
    if post.is_pinned and _pinned_count(post.channel, exclude_id=post.id) >= MAX_PINNED:
        return _err("too_many_pinned", "Three posts are already pinned. Unpin one first.", 400)
    post.save()
    return Response(_serialize([post], request.user, role)[0])


@api_view(["POST"])
@permission_classes(PERMS)
def post_ack(request, pk):
    sid, role, bad = _ctx(request)
    if bad:
        return bad
    post = _visible_post(sid, role, pk)
    if post is None:
        return _err("not_found", "Post not found.", 404)
    ConnectAck.objects.get_or_create(post=post, user=request.user)
    out = {"acknowledged": True}
    if role == ADMIN:
        out["ack_count"] = ConnectAck.objects.filter(post=post).count()
    return Response(out)


@api_view(["POST"])
@permission_classes(PERMS)
def post_report(request, pk):
    sid, role, bad = _ctx(request)
    if bad:
        return bad
    post = _visible_post(sid, role, pk)
    if post is None:
        return _err("not_found", "Post not found.", 404)
    if post.author_id == request.user.id:
        return _err("own_post", "You cannot report your own post.", 400)
    slow = _slow(request)
    if slow:
        return slow
    reason = str(request.data.get("reason") or "").strip()[:200]
    _, created = ConnectReport.objects.get_or_create(post=post, reporter=request.user, defaults={"reason": reason})
    return Response({"reported": True}, status=201 if created else 200)


@api_view(["GET"])
@permission_classes(PERMS)
def reports(request):
    sid, role, bad = _ctx(request)
    if bad:
        return bad
    if role != ADMIN:
        return _err("forbidden", "Only a school administrator can see reports.", 403)
    rows = list(
        ConnectReport.objects.filter(post__channel__school_id=sid, resolved=False)
        .select_related("post")
        .order_by("-id")[:50]
    )
    posts = _serialize([r.post for r in rows], request.user, role)
    by_id = {p["id"]: p for p in posts}
    return Response(
        {
            "reports": [
                {
                    "id": r.id,
                    "reason": r.reason,
                    "created_at": r.created_at.isoformat(),
                    "post": by_id[r.post_id],
                }
                for r in rows
            ]
        }
    )


@api_view(["POST"])
@permission_classes(PERMS)
def report_resolve(request, pk):
    sid, role, bad = _ctx(request)
    if bad:
        return bad
    if role != ADMIN:
        return _err("forbidden", "Only a school administrator can resolve reports.", 403)
    report = ConnectReport.objects.select_related("post").filter(pk=pk, post__channel__school_id=sid).first()
    if report is None:
        return _err("not_found", "Report not found.", 404)
    post = report.post
    if _flag(request.data.get("hide")):
        post.is_hidden = True
        post.is_pinned = False
        post.hidden_by = request.user
        post.save(update_fields=["is_hidden", "is_pinned", "hidden_by"])
    count = ConnectReport.objects.filter(post=post, resolved=False).update(resolved=True, resolved_by=request.user)
    return Response({"resolved": count})


@api_view(["GET"])
@permission_classes(PERMS)
def members(request):
    sid, role, bad = _ctx(request)
    if bad:
        return bad
    staff = {}
    for profile in StaffProfile.objects.filter(school_id=sid).select_related("user"):
        staff[profile.user_id] = (profile.user, profile.role)
    for model, label in ((TeacherProfile, "teacher"), (SchoolAdminProfile, "admin")):
        ids = model.objects.filter(school_id=sid).values("user_id")
        for u in User.objects.filter(id__in=ids):
            staff[u.id] = (u, label)
    active = Enrollment.objects.filter(is_active=True, student__school_id=sid).values("student_id")
    linked = StudentGuardian.objects.filter(student_id__in=active).values("guardian_id")
    parent_ids = GuardianProfile.objects.filter(school_id=sid, id__in=linked).values("user_id")
    parents = User.objects.filter(id__in=parent_ids)
    parent_count = parents.count()
    rows = [(u, label) for u, label in staff.values()]
    truncated = False
    if role == ADMIN:
        q = (request.query_params.get("q") or "").strip()[:60]
        if q:
            parents = parents.filter(Q(first_name__icontains=q) | Q(last_name__icontains=q))
        parents = parents.exclude(id__in=list(staff.keys()))
        chosen = list(parents.order_by("first_name", "last_name", "id")[:101])
        truncated = len(chosen) > 100
        rows += [(u, PARENT) for u in chosen[:100]]
    muted = set(ConnectMute.objects.filter(school_id=sid).values_list("user_id", flat=True))
    out = []
    for u, label in rows:
        item = {"name": display_name(u, label), "role": label}
        if role == ADMIN:
            item["user_id"] = u.id
            item["muted"] = u.id in muted
        out.append(item)
    out.sort(
        key=lambda m: (
            m["role"] != "admin",
            m["role"] != "teacher",
            m["role"] not in ("bursar", "secretary"),
            m["name"].lower(),
        )
    )
    return Response({"members": out, "parent_count": parent_count, "truncated": truncated})


@api_view(["POST", "DELETE"])
@permission_classes(PERMS)
def member_mute(request, user_id):
    sid, role, bad = _ctx(request)
    if bad:
        return bad
    if role != ADMIN:
        return _err("forbidden", "Only a school administrator can mute a member.", 403)
    target = User.objects.filter(pk=user_id).first()
    t_sid, t_role = membership(target) if target else (None, None)
    if t_sid != sid or t_role is None:
        return _err("not_found", "Member not found.", 404)
    if t_role == ADMIN:
        return _err("not_allowed", "Administrators cannot be muted.", 400)
    if request.method == "DELETE":
        ConnectMute.objects.filter(school_id=sid, user=target).delete()
        return Response(status=204)
    _, created = ConnectMute.objects.get_or_create(school_id=sid, user=target, defaults={"created_by": request.user})
    return Response({"muted": True}, status=201 if created else 200)


# ---- Connect attachments ----
from urllib.parse import quote

MAX_FILE = 5 * 1024 * 1024
MAX_FILES = 4
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _sniff(head, name):
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head.startswith(b"%PDF"):
        return "application/pdf"
    if head.startswith(b"PK\x03\x04"):
        return {"docx": DOCX, "xlsx": XLSX}.get(ext)
    if head.startswith(b"\xd0\xcf\x11\xe0"):
        return {"doc": "application/msword", "xls": "application/vnd.ms-excel"}.get(ext)
    # Voice notes: checked by content, never by file name.
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        return "audio/webm"
    if head.startswith(b"OggS"):
        return "audio/ogg"
    if head[4:8] == b"ftyp":
        return "audio/mp4"
    if head.startswith(b"ID3") or head[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return "audio/mpeg"
    return None


def _read_files(request):
    out = []
    for f in request.FILES.getlist("files"):
        if len(out) >= MAX_FILES:
            return None, _err("too_many_files", "You can attach up to 4 files to one message.", 400)
        if f.size > MAX_FILE:
            return None, _err("file_too_big", "Each file must be 5 MB or smaller.", 400)
        name = "".join(c for c in (f.name or "file").replace("\\", "/").split("/")[-1] if c.isprintable())[:200] or "file"
        head = f.read(16)
        f.seek(0)
        kind = _sniff(head, name)
        if kind is None:
            return None, _err("bad_file", "This file type is not allowed. Use photos, voice notes, PDF, Word or Excel files.", 400)
        out.append({"name": name, "content_type": kind, "size": f.size, "data": f.read()})
    return out, None


@api_view(["GET"])
@permission_classes(PERMS)
def attachment_file(request, pk):
    sid, role, bad = _ctx(request)
    if bad:
        return bad
    att = ConnectAttachment.objects.filter(pk=pk).first()
    if att is None or _visible_post(sid, role, att.post_id) is None:
        return _err("not_found", "File not found.", 404)
    resp = HttpResponse(bytes(att.data), content_type=att.content_type)
    inline = att.content_type.startswith(("image/", "audio/"))
    disp = "inline" if inline else "attachment"
    resp["Content-Disposition"] = f"{disp}; filename*=UTF-8''{quote(att.name)}"
    resp["X-Content-Type-Options"] = "nosniff"
    resp["Cache-Control"] = "private, max-age=3600"
    return resp


# ---- Connect profile pictures ----
from schools.models import ConnectAvatar

MAX_AVATAR = 1024 * 1024
AVATAR_TYPES = ("image/jpeg", "image/png", "image/webp")


@api_view(["GET", "POST", "DELETE"])
@permission_classes(PERMS)
def my_avatar(request):
    sid, role, bad = _ctx(request)
    if bad:
        return bad
    if request.method == "GET":
        av = ConnectAvatar.objects.filter(user=request.user).first()
        if av is None:
            return _err("not_found", "No picture.", 404)
        resp = HttpResponse(bytes(av.data), content_type=av.content_type)
        resp["Content-Disposition"] = "inline"
        resp["X-Content-Type-Options"] = "nosniff"
        resp["Cache-Control"] = "private, no-cache"
        return resp
    if request.method == "DELETE":
        ConnectAvatar.objects.filter(user=request.user).delete()
        return Response(status=204)
    f = request.FILES.get("file")
    if f is None:
        return _err("no_file", "Choose a photo.", 400)
    if f.size > MAX_AVATAR:
        return _err("file_too_big", "The picture must be 1 MB or smaller.", 400)
    head = f.read(16)
    f.seek(0)
    kind = _sniff(head, f.name or "")
    if kind not in AVATAR_TYPES:
        return _err("bad_file", "Use a JPEG, PNG or WebP photo.", 400)
    ConnectAvatar.objects.update_or_create(
        user=request.user,
        defaults={"content_type": kind, "size": f.size, "data": f.read()},
    )
    return Response({"ok": True})


@api_view(["GET"])
@permission_classes(PERMS)
def post_avatar(request, pk):
    sid, role, bad = _ctx(request)
    if bad:
        return bad
    post = _visible_post(sid, role, pk)
    author_id = getattr(post, "author_id", None)
    av = ConnectAvatar.objects.filter(user_id=author_id).first() if author_id else None
    if av is None:
        return _err("not_found", "No picture.", 404)
    resp = HttpResponse(bytes(av.data), content_type=av.content_type)
    resp["Content-Disposition"] = "inline"
    resp["X-Content-Type-Options"] = "nosniff"
    resp["Cache-Control"] = "private, max-age=3600"
    return resp
