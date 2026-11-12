"""Save step for the Migration Centre.

The upload is checked again on the server, so nothing from the browser is trusted.
Only learners whose status is "ready" are added, all in one transaction.

Repeating the same request is safe: the browser sends a request id, and a second
request with the same id returns the first result instead of adding the learners
twice. This covers a dropped connection after the save had already committed.
"""
import re

from django.db import DatabaseError, IntegrityError, transaction
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiTypes
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from schools.models import AcademicYear, Enrollment, MarkAuditLog, School, Student

from .migration_check import UploadError, build_existing, build_structure, read_request
from .migration_rules import analyse_upload
from .student_import import _admin
from .views import _scope

CHUNK = 400
AUDIT_ACTION = "student_migration_import"
REQUEST_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


class SaveError(Exception):
    pass


def _save(school_id, year, ready):
    if any(not r.get("admission_number") or not r.get("level_id") for r in ready):
        raise SaveError("A learner had no admission number or class. Nothing was added.")
    Student.objects.bulk_create([
        Student(school_id=school_id, first_name=r["first_name"], last_name=r["last_name"],
                admission_number=r["admission_number"],
                assessment_number=r.get("assessment_number") or "")
        for r in ready], batch_size=CHUNK)
    adms = [r["admission_number"] for r in ready]
    ids = {}
    for i in range(0, len(adms), CHUNK):
        found = Student.objects.filter(school_id=school_id, admission_number__in=adms[i:i + CHUNK])
        for s in found.values("id", "admission_number"):
            ids[s["admission_number"]] = s["id"]
    if len(ids) != len(ready):
        raise SaveError("Could not match the saved learners. Nothing was added.")
    Enrollment.objects.bulk_create([
        Enrollment(student_id=ids[r["admission_number"]], academic_year=year,
                   class_level_id=r["level_id"], stream_id=r.get("stream_id"), is_active=True)
        for r in ready], batch_size=CHUNK)


def _summary(result, ready):
    by_class = {}
    for r in ready:
        by_class[r["class_label"]] = by_class.get(r["class_label"], 0) + 1
    return {
        "created": len(ready),
        "skipped": result["summary"]["skipped"],
        "duplicates": result["summary"]["duplicates"],
        "blocked": result["summary"]["blocked"],
        "needs_confirmation": result["summary"]["needs_confirmation"],
        "temporary_admission": sum(1 for r in ready if r["provisional_admission"]),
        "by_class": by_class,
    }


@extend_schema(request=OpenApiTypes.OBJECT, responses={
    201: OpenApiResponse(description="Ready learners were added."),
    200: OpenApiResponse(description="This import was already saved earlier."),
    400: OpenApiResponse(description="Nothing was added."),
    403: OpenApiResponse(description="Administrator authorization required."),
    409: OpenApiResponse(description="The learners were added by someone else in the meantime.")})
@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser])
def migration_commit(request):
    school_id, error = _scope(request)
    if error:
        return error
    if not _admin(request.user):
        return Response({"detail": "Only school administrators can add learners."}, status=403)
    if school_id is None:
        raw = request.data.get("school_id")
        if not str(raw or "").isdigit() or not School.objects.filter(pk=int(raw)).exists():
            return Response({"detail": "Choose a school."}, status=400)
        school_id = int(raw)
    try:
        data = read_request(request)
    except UploadError as exc:
        return Response({"detail": str(exc)}, status=400)
    request_id = str(request.data.get("request_id") or "").strip()
    if request_id and not REQUEST_ID.match(request_id):
        return Response({"detail": "The import id was not valid."}, status=400)
    year = AcademicYear.objects.filter(school_id=school_id, is_active=True).first()
    if year is None:
        return Response({"detail": "Set an active academic year before adding learners. Nothing was added."}, status=400)
    try:
        with transaction.atomic():
            School.objects.select_for_update().filter(pk=school_id).first()
            if request_id:
                done = MarkAuditLog.objects.filter(
                    school_id=school_id, action=AUDIT_ACTION, details__request_id=request_id).first()
                if done is not None:
                    previous = dict(done.details.get("result") or {})
                    previous["already_saved"] = True
                    return Response(previous, status=200)
            result = analyse_upload(
                data["matrix"], build_structure(school_id), existing=build_existing(school_id),
                source=data["source"], name_order=data["name_order"],
                default_class=data["default_class"], confirmations=data["confirmations"],
                fixes=data["fixes"], mapping=data["mapping"], header_row=data["header_row"])
            if any(i.get("severity") == "block" for i in result["file_issues"]):
                return Response({"detail": "The file still has a problem. Check the list again and fix it first. Nothing was added."}, status=400)
            ready = [r for r in result["rows"] if r["status"] == "ready"]
            if not ready:
                return Response({"detail": "No learners are ready to add. Nothing was added."}, status=400)
            summary = _summary(result, ready)
            _save(school_id, year, ready)
            summary["request_id"] = request_id or ""
            summary["committed"] = True
            MarkAuditLog.objects.create(
                school_id=school_id, user=request.user, action=AUDIT_ACTION,
                details={"added": len(ready), "left_out": summary["skipped"],
                         "duplicates": summary["duplicates"], "source": data["source"],
                         "classes": summary["by_class"], "request_id": request_id or "",
                         "file": getattr(data["upload"], "name", "") or "pasted text",
                         "result": summary})
    except IntegrityError:
        return Response({"detail": "Some of these admission numbers were added while you were working. "
                                   "Nothing was added now. Check the list again to see what is left."}, status=409)
    except SaveError as exc:
        return Response({"detail": str(exc)}, status=500)
    except DatabaseError:
        return Response({"detail": "Saving failed, so nothing was added. Check the list and try again."}, status=500)
    return Response(summary, status=201)
