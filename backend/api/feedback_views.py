import sys

from django.db import IntegrityError, transaction
from django.db.models import Avg, Count
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle

from api.connect_rules import ROLE_LABEL, membership
from api.suspension import SchoolNotSuspended
from schools.models import FeedbackEntry

PERMS = [IsAuthenticated, SchoolNotSuspended]
OWNER_PERMS = [IsAuthenticated]
PAGE = 30
MAX_TEXT = 1000
MAX_PER_USER = 100
KINDS = [k for k, _ in FeedbackEntry.KINDS]


class FeedbackThrottle(SimpleRateThrottle):
    scope = "feedback_post"
    rate = "1000/min" if "test" in sys.argv else "20/hour"

    def get_cache_key(self, request, view):
        if request.method != "POST":
            return None
        if not request.user or not request.user.is_authenticated:
            return None
        return self.cache_format % {"scope": self.scope, "ident": request.user.pk}


def _err(code, message, status):
    return Response({"error": code, "message": message}, status=status)


def _int(value, default=None):
    if isinstance(value, bool):
        return default
    if isinstance(value, float):
        return int(value) if value.is_integer() else default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _row(e, owner_view=False):
    row = {
        "id": e.id,
        "kind": e.kind,
        "rating": e.rating,
        "text": e.text,
        "created_at": e.created_at.isoformat(),
        "updated_at": e.updated_at.isoformat(),
    }
    if owner_view:
        row["is_read"] = e.is_read
        row["school"] = e.school.name if e.school_id else None
        row["role"] = ROLE_LABEL.get(e.role, "")
        row["author"] = e.user.get_full_name() or "Member"
    return row


def _parse(request):
    data = request.data
    if not hasattr(data, "get"):
        return None, _err("invalid_body", "Send the feedback as a form or JSON object.", 400)
    kind = data.get("kind")
    if kind not in KINDS:
        return None, _err("invalid_kind", "Choose rating, idea, problem or review.", 400)
    text = data.get("text", "")
    if text is None:
        text = ""
    if not isinstance(text, str):
        return None, _err("invalid_text", "Text must be words.", 400)
    text = text.strip()
    if len(text) > MAX_TEXT:
        return None, _err("text_too_long", "Please keep it under %d characters." % MAX_TEXT, 400)
    rating = None
    if kind == "rating":
        rating = _int(data.get("rating"))
        if rating is None or not 1 <= rating <= 5:
            return None, _err("invalid_rating", "Rating must be a whole number from 1 to 5.", 400)
    elif not text:
        return None, _err("text_required", "Please write something.", 400)
    return {"kind": kind, "rating": rating, "text": text}, None


def _owner_only(request):
    if not request.user.is_superuser:
        return _err("forbidden", "Only the Marian owner can read all feedback.", 403)
    return None


@api_view(["GET", "POST"])
@permission_classes(PERMS)
@throttle_classes([FeedbackThrottle])
def feedback(request):
    sid, role = membership(request.user)
    if sid is None:
        return _err("no_access", "Feedback is for school staff and parents linked to a learner.", 403)
    mine = FeedbackEntry.objects.filter(user=request.user)
    if request.method == "GET":
        return Response({"results": [_row(e) for e in mine[:100]]})
    clean, bad = _parse(request)
    if bad:
        return bad
    if clean["kind"] == "rating":
        entry = mine.filter(kind="rating").first()
        if entry is None:
            try:
                with transaction.atomic():
                    entry = FeedbackEntry.objects.create(user=request.user, school_id=sid, role=role, **clean)
                return Response(_row(entry), status=201)
            except IntegrityError:
                entry = mine.filter(kind="rating").first()
        if entry is None:
            return _err("try_again", "Please try again.", 409)
        entry.rating = clean["rating"]
        entry.text = clean["text"]
        entry.school_id = sid
        entry.role = role
        entry.is_read = False
        entry.save()
        return Response(_row(entry), status=200)
    if mine.exclude(kind="rating").count() >= MAX_PER_USER:
        return _err("limit_reached", "You have sent the most feedback allowed.", 400)
    entry = FeedbackEntry.objects.create(user=request.user, school_id=sid, role=role, **clean)
    return Response(_row(entry), status=201)


@api_view(["DELETE"])
@permission_classes(PERMS)
def feedback_detail(request, pk):
    deleted, _ = FeedbackEntry.objects.filter(pk=pk, user=request.user).delete()
    if not deleted:
        return _err("not_found", "Feedback not found.", 404)
    return Response(status=204)


@api_view(["GET"])
@permission_classes(OWNER_PERMS)
def feedback_all(request):
    denied = _owner_only(request)
    if denied:
        return denied
    qs = FeedbackEntry.objects.select_related("school", "user")
    kind = request.GET.get("kind")
    if kind:
        if kind not in KINDS:
            return _err("invalid_kind", "Choose rating, idea, problem or review.", 400)
        qs = qs.filter(kind=kind)
    if request.GET.get("unread") == "1":
        qs = qs.filter(is_read=False)
    page = min(max(_int(request.GET.get("page"), 1), 1), 100000)
    total = qs.count()
    start = (page - 1) * PAGE
    return Response({
        "count": total,
        "page": page,
        "page_size": PAGE,
        "results": [_row(e, True) for e in qs[start:start + PAGE]],
    })


@api_view(["POST"])
@permission_classes(OWNER_PERMS)
def feedback_read(request, pk):
    denied = _owner_only(request)
    if denied:
        return denied
    entry = FeedbackEntry.objects.filter(pk=pk).first()
    if entry is None:
        return _err("not_found", "Feedback not found.", 404)
    flag = request.data.get("read", True) if hasattr(request.data, "get") else True
    if isinstance(flag, str):
        flag = flag.strip().lower() in ("1", "true", "yes")
    entry.is_read = bool(flag)
    entry.save(update_fields=["is_read"])
    return Response(_row(entry, True))


@api_view(["GET"])
@permission_classes(OWNER_PERMS)
def feedback_summary(request):
    denied = _owner_only(request)
    if denied:
        return denied
    ratings = FeedbackEntry.objects.filter(kind="rating", rating__isnull=False).order_by()
    agg = ratings.aggregate(n=Count("id"), avg=Avg("rating"))
    stars = {str(i): 0 for i in range(1, 6)}
    for row in ratings.values("rating").annotate(c=Count("id")).order_by():
        stars[str(row["rating"])] = row["c"]
    schools = ratings.exclude(school__isnull=True).values("school").distinct().count()
    return Response({
        "ratings": agg["n"],
        "average": round(agg["avg"], 1) if agg["n"] else None,
        "by_star": stars,
        "schools": schools,
        "unread": FeedbackEntry.objects.filter(is_read=False).count(),
        "total": FeedbackEntry.objects.count(),
    })
