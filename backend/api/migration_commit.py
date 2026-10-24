"""Save step for the Migration Centre.

The upload is checked again on the server, so nothing from the browser is trusted.
Only learners whose status is "ready" are added, all in one transaction.
"""
from django.db import DatabaseError, transaction
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiTypes
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from schools.models import AcademicYear, Enrollment, MarkAuditLog, School, Student

from .migration_check import UploadError, _confirmations, _fixes, build_existing, build_structure, parse_table
from .migration_rules import analyse_upload
from .student_import import _admin
from .views import _scope

CHUNK = 400


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


@extend_schema(request=OpenApiTypes.OBJECT, responses={
    201: OpenApiResponse(description="Ready learners were added."),
    400: OpenApiResponse(description="Nothing was added."),
    403: OpenApiResponse(description="Administrator authorization required.")})
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
    upload = request.FILES.get("file")
    text = request.data.get("text", "")
    if upload is None and not str(text).strip():
        return Response({"detail": "Attach a file or paste the table."}, status=400)
    source = request.data.get("source", "digital")
    if source not in ("digital", "paper"):
        return Response({"detail": "Unknown source."}, status=400)
    try:
        matrix = parse_table(upload, text)
        confirmations = _confirmations(request.data.get("confirmations"))
        fixes = _fixes(request.data.get("fixes"))
    except UploadError as exc:
        return Response({"detail": str(exc)}, status=400)
    year = AcademicYear.objects.filter(school_id=school_id, is_active=True).first()
    if year is None:
        return Response({"detail": "Set an active academic year before adding learners. Nothing was added."}, status=400)
    try:
        with transaction.atomic():
            School.objects.select_for_update().filter(pk=school_id).first()
            result = analyse_upload(
                matrix, build_structure(school_id), existing=build_existing(school_id), source=source,
                name_order=request.data.get("name_order") or None,
                default_class=str(request.data.get("default_class") or ""),
                confirmations=confirmations, fixes=fixes)
            if any(i.get("severity") == "block" for i in result["file_issues"]):
                return Response({"detail": "The file has problems. Check the list again and fix them first. Nothing was added."}, status=400)
            ready = [r for r in result["rows"] if r["status"] == "ready"]
            skipped = len(result["rows"]) - len(ready)
            if not ready:
                return Response({"detail": "No learners are ready to add. Nothing was added."}, status=400)
            _save(school_id, year, ready)
            MarkAuditLog.objects.create(
                school_id=school_id, user=request.user, action="student_migration_import",
                details={"added": len(ready), "left_out": skipped, "source": source,
                         "file": getattr(upload, "name", "") or "pasted text"})
    except SaveError as exc:
        return Response({"detail": str(exc)}, status=500)
    except DatabaseError:
        return Response({"detail": "Saving failed, so nothing was added. Check the list and try again."}, status=500)
    return Response({"created": len(ready), "skipped": skipped, "committed": True}, status=201)
