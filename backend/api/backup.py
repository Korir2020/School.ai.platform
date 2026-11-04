"""Data backup and restoration.

Full platform backup (superadmin, or `manage.py backup_data`):
  a gzip file holding {"meta": {...}, "objects": [...]} where objects is
  standard Django dumpdata output and meta carries a SHA-256 checksum,
  per-model counts and the migration state it was taken at.
Restore only through `manage.py restore_data` (needs shell access and an
explicit --yes), never through the web: a wrong click must not wipe a school.

School export (non-deputy school administrator): every record that belongs
to the school, as readable JSON, for the school's own safekeeping. Password
hashes and other schools' data are never included.
"""
import gzip
import hashlib
import io
import json

from django.apps import apps
from django.core import serializers
from django.core.management import call_command
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from schools.models import MarkAuditLog, School, SchoolAdminProfile

from .permissions import IsSuperAdmin

FORMAT = "marian-backup"
VERSION = 1
EXCLUDE = ["contenttypes", "auth.permission", "sessions", "admin.logentry",
           "token_blacklist"]
MAX_UPLOAD = 200 * 1024 * 1024


def _excluded():
    out = []
    for label in EXCLUDE:
        app = label.split(".")[0]
        if apps.is_installed(app) or any(c.label == app for c in apps.get_app_configs()):
            out.append(label)
    return out


def migration_state():
    rows = MigrationRecorder(connection).migration_qs.values_list("app", "name")
    last = {}
    for app, name in rows:
        if name > last.get(app, ""):
            last[app] = name
    return last


def _digest(objects_json):
    return hashlib.sha256(objects_json.encode("utf-8")).hexdigest()


def build_full_backup():
    """Return (gzip_bytes, meta)."""
    buf = io.StringIO()
    call_command("dumpdata", exclude=_excluded(), natural_foreign=True, stdout=buf, verbosity=0)
    objects_json = buf.getvalue() or "[]"
    objects = json.loads(objects_json)
    canon = json.dumps(objects, sort_keys=True, separators=(",", ":"))
    counts = {}
    for o in objects:
        counts[o["model"]] = counts.get(o["model"], 0) + 1
    meta = {"format": FORMAT, "version": VERSION, "created_at": timezone.now().isoformat(),
            "migrations": migration_state(), "counts": counts, "total": len(objects),
            "sha256": _digest(canon)}
    raw = json.dumps({"meta": meta, "objects": objects}, separators=(",", ":")).encode("utf-8")
    return gzip.compress(raw, compresslevel=6), meta


def read_backup(data):
    """Parse and check a backup file's bytes. Returns (doc, report).
    report = {ok, problems[], warnings[], meta}."""
    problems, warnings = [], []
    try:
        raw = gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data
        doc = json.loads(raw.decode("utf-8"))
    except Exception:
        return None, {"ok": False, "problems": ["This is not a Marian backup file (it could not be read)."], "warnings": [], "meta": None}
    meta = doc.get("meta") if isinstance(doc, dict) else None
    objects = doc.get("objects") if isinstance(doc, dict) else None
    if not meta or meta.get("format") != FORMAT or not isinstance(objects, list):
        return None, {"ok": False, "problems": ["This is not a Marian backup file."], "warnings": [], "meta": None}
    if meta.get("version") != VERSION:
        problems.append(f"Backup format version {meta.get('version')} is not supported by this server.")
    canon = json.dumps(objects, sort_keys=True, separators=(",", ":"))
    if _digest(canon) != meta.get("sha256"):
        problems.append("The checksum does not match: the file is damaged or was edited.")
    if len(objects) != meta.get("total"):
        problems.append("The number of records does not match the backup summary.")
    unknown = sorted({o.get("model", "?") for o in objects if not _model_exists(o.get("model", ""))})
    if unknown:
        problems.append("Unknown record types: " + ", ".join(unknown[:10]))
    now = migration_state()
    for app, name in (meta.get("migrations") or {}).items():
        if app in now and now[app] != name:
            warnings.append(f"{app}: backup taken at {name}, this server is at {now[app]}. "
                            "Restore into a server running the same version, then migrate.")
    return doc, {"ok": not problems, "problems": problems, "warnings": warnings, "meta": meta}


def _model_exists(label):
    try:
        apps.get_model(label)
        return True
    except (LookupError, ValueError):
        return False


# ---- per-school export ------------------------------------------------

def _school_path(model, depth=0, seen=None):
    """Find an ORM lookup from model to School, for example "student__school"."""
    if model is School:
        return "pk"
    seen = (seen or set()) | {model}
    fks = [f for f in model._meta.get_fields()
           if getattr(f, "many_to_one", False) and f.concrete and f.related_model is not None]
    for f in fks:
        if f.related_model is School:
            return f.name
    if depth >= 3:
        return None
    for f in fks:
        if f.related_model in seen or f.related_model._meta.app_label != "schools":
            continue
        sub = _school_path(f.related_model, depth + 1, seen)
        if sub:
            return f"{f.name}__{sub}"
    return None


SKIP_EXPORT = {"SchoolRegistration", "SuperadminSecurity", "DemoRequest"}


def school_export(school):
    data, counts = {}, {}
    user_ids = set()
    for model in apps.get_app_config("schools").get_models():
        if model.__name__ in SKIP_EXPORT:
            continue
        path = _school_path(model)
        if not path:
            continue
        qs = model.objects.filter(**{path: school.pk}) if path != "pk" else model.objects.filter(pk=school.pk)
        rows = json.loads(serializers.serialize("json", qs))
        for r in rows:
            fields = r["fields"]
            for k in ("user", "recipient", "recorded_by", "created_by", "author"):
                if isinstance(fields.get(k), int):
                    user_ids.add(fields[k])
        data[model.__name__] = rows
        counts[model.__name__] = len(rows)
    from django.contrib.auth import get_user_model
    User = get_user_model()
    data["Accounts"] = [{"id": u.id, "username": u.username, "first_name": u.first_name,
                         "last_name": u.last_name, "email": u.email, "is_active": u.is_active}
                        for u in User.objects.filter(id__in=user_ids).order_by("id")]
    counts["Accounts"] = len(data["Accounts"])
    return {"meta": {"format": "marian-school-export", "version": 1, "school": school.name,
                     "school_code": school.code, "created_at": timezone.now().isoformat(),
                     "counts": counts,
                     "note": "Passwords are never exported. Keep this file private: it holds learner records."},
            "data": data}


# ---- views ------------------------------------------------------------

def _stamp():
    return timezone.now().strftime("%Y%m%d-%H%M")


@api_view(["GET"])
@permission_classes([IsSuperAdmin])
def full_backup(request):
    blob, meta = build_full_backup()
    MarkAuditLog.objects.create(user=request.user, action="backup_downloaded",
                                details={"records": meta["total"], "sha256": meta["sha256"]})
    resp = HttpResponse(blob, content_type="application/gzip")
    resp["Content-Disposition"] = f'attachment; filename="marian-backup-{_stamp()}.json.gz"'
    resp["X-Backup-Sha256"] = meta["sha256"]
    return resp


@api_view(["POST"])
@permission_classes([IsSuperAdmin])
@parser_classes([MultiPartParser])
def validate_backup(request):
    f = request.FILES.get("file")
    if not f:
        return Response({"detail": "Choose a backup file."}, status=400)
    if f.size > MAX_UPLOAD:
        return Response({"detail": "The file is larger than 200 MB."}, status=400)
    _, report = read_backup(f.read())
    return Response(report)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def backup_status(request):
    if not request.user.is_superuser:
        return Response({"detail": "Platform administrators only."}, status=403)
    last = MarkAuditLog.objects.filter(action__in=["backup_downloaded", "backup_created"]).order_by("-timestamp").first()
    return Response({"last_backup": last.timestamp if last else None,
                     "last_backup_by": last.user.username if last and last.user else None,
                     "migrations": migration_state()})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def school_export_view(request):
    boss = SchoolAdminProfile.objects.filter(user=request.user, is_deputy=False).select_related("school").first()
    if not boss:
        return Response({"detail": "Only the school administrator can export the school's data."}, status=403)
    doc = school_export(boss.school)
    MarkAuditLog.objects.create(school=boss.school, user=request.user, action="school_data_exported",
                                details={"counts": doc["meta"]["counts"]})
    body = json.dumps(doc, indent=1, default=str).encode("utf-8")
    resp = HttpResponse(body, content_type="application/json")
    resp["Content-Disposition"] = f'attachment; filename="{boss.school.code}-export-{_stamp()}.json"'
    return resp
