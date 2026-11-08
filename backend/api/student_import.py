import csv
import io
from collections import defaultdict

from django.db import transaction
from django.http import HttpResponse
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiTypes

from schools.models import (
    AcademicYear, CurriculumPathway, Enrollment, SchoolAdminProfile, Student, Stream,
)
from .senior_rules import is_cbc_senior, pathway_matches_class
from .views import _scope

_HEADERS = ["first_name", "last_name", "admission_number", "class_level", "stream", "pathway"]
_REQUIRED_HEADERS = _HEADERS[:-1]


def _admin(request):
    return request.is_superuser or SchoolAdminProfile.objects.filter(user=request).exists()


@extend_schema(request=OpenApiTypes.OBJECT, responses={200: OpenApiResponse(description="CSV preview or student roster export."), 201: OpenApiResponse(description="Validated student rows committed."), 400: OpenApiResponse(description="CSV validation failure."), 403: OpenApiResponse(description="Administrator authorization required."), 413: OpenApiResponse(description="CSV exceeds the 5 MB upload limit.")})
@api_view(["GET", "POST"])
@parser_classes([MultiPartParser, FormParser])
def student_import(request):
    school_id, error = _scope(request)
    if error: return error
    if not _admin(request.user): return Response({"detail": "Only school administrators can import students."}, status=403)
    if request.method == "GET":
        rows = Student.objects.filter(school_id=school_id).select_related("school") if school_id else Student.objects.all()
        enrollments = {}
        enrollment_rows = Enrollment.objects.filter(is_active=True)
        if school_id is not None:
            enrollment_rows = enrollment_rows.filter(student__school_id=school_id)
        for enrollment in enrollment_rows.select_related(
            "student", "class_level", "stream", "pathway").order_by("student_id", "-id"):
            enrollments.setdefault(enrollment.student_id, enrollment)
        out = io.StringIO(); writer = csv.writer(out); writer.writerow(_HEADERS)
        for student in rows.order_by("last_name", "first_name"):
            enrollment = enrollments.get(student.pk)
            writer.writerow([student.first_name, student.last_name, student.admission_number,
                             enrollment.class_level.name if enrollment else "",
                             enrollment.stream.name if enrollment and enrollment.stream else "",
                             enrollment.pathway.code if enrollment and enrollment.pathway else ""])
        response = HttpResponse(out.getvalue(), content_type="text/csv"); response["Content-Disposition"] = 'attachment; filename="students.csv"'; return response
    upload = request.FILES.get("file")
    if not upload: return Response({"detail": "Attach a CSV file."}, status=400)
    if upload.size > 5 * 1024 * 1024: return Response({"detail": "CSV files must be 5 MB or smaller."}, status=413)
    try: rows = list(csv.DictReader(io.TextIOWrapper(upload.file, encoding="utf-8-sig")))
    except (UnicodeDecodeError, csv.Error): return Response({"detail": "The file must be a valid UTF-8 CSV."}, status=400)
    missing = [x for x in _REQUIRED_HEADERS if x not in (rows[0].keys() if rows else [])]
    if missing: return Response({"detail": f"Missing columns: {', '.join(missing)}"}, status=400)
    errors, valid = [], []
    import_year = AcademicYear.objects.filter(school_id=school_id, is_active=True).order_by("id").first()
    existing_rows = Student.objects.all()
    stream_rows = Stream.objects.filter(is_active=True)
    if school_id is not None:
        existing_rows = existing_rows.filter(school_id=school_id)
        stream_rows = stream_rows.filter(school_id=school_id)
    admission_numbers = set(existing_rows.values_list("admission_number", flat=True))
    streams_by_name = defaultdict(list)
    for stream in stream_rows.select_related(
        "class_level__curriculum").order_by("class_level__level_number", "name", "id"):
        streams_by_name[stream.name.lower()].append(stream)
    pathways_by_grade = defaultdict(dict)
    for pathway in CurriculumPathway.objects.filter(is_active=True).select_related(
        "curriculum").prefetch_related("class_levels"):
        for level in pathway.class_levels.all():
            pathways_by_grade[level.pk][pathway.code.lower()] = pathway
            pathways_by_grade[level.pk][pathway.name.lower()] = pathway
    for index, row in enumerate(rows, start=2):
        values = {k: (row.get(k) or "").strip() for k in _HEADERS}
        if not values["first_name"] or not values["last_name"] or not values["admission_number"]: errors.append({"row": index, "error": "First name, last name, and admission number are required."}); continue
        if values["admission_number"] in admission_numbers: errors.append({"row": index, "error": "Admission number already exists."}); continue
        stream = None
        if values["stream"]:
            matches = streams_by_name.get(values["stream"].lower(), [])
            stream = next((candidate for candidate in matches if not values["class_level"]
                           or candidate.class_level.name.lower() == values["class_level"].lower()), None)
        if values["stream"] and not stream: errors.append({"row": index, "error": f"Stream not found: {values['stream']}"}); continue
        if values["class_level"] and stream and stream.class_level.name.lower() != values["class_level"].lower(): errors.append({"row": index, "error": "Class level does not match the stream."}); continue
        pathway = None
        if stream and import_year and is_cbc_senior(stream.class_level):
            if not values["pathway"]:
                errors.append({"row": index, "error": "The pathway column is required for CBC Senior enrollments."}); continue
            pathway = pathways_by_grade.get(stream.class_level_id, {}).get(values["pathway"].lower())
            if pathway is None or not pathway_matches_class(pathway, stream.class_level):
                errors.append({"row": index, "error": f"Pathway not found or not valid for this grade: {values['pathway']}"}); continue
        elif values["pathway"]:
            errors.append({"row": index, "error": "Only CBC Senior enrollments accept a pathway value."}); continue
        valid.append({**values, "stream_obj": stream, "pathway_obj": pathway})
        admission_numbers.add(values["admission_number"])
    commit = str(request.data.get("commit", "false")).lower() == "true"
    if errors or not commit: return Response({"preview": [{k: v for k, v in row.items() if k not in {"stream_obj", "pathway_obj"}} for row in valid], "errors": errors, "ready": not errors and bool(valid), "committed": False})
    with transaction.atomic():
        for row in valid:
            student = Student.objects.create(school_id=school_id, first_name=row["first_name"], last_name=row["last_name"], admission_number=row["admission_number"])
            if row["stream_obj"]:
                if import_year: Enrollment.objects.create(student=student, academic_year=import_year, class_level=row["stream_obj"].class_level, stream=row["stream_obj"], pathway=row["pathway_obj"], is_active=True)
    return Response({"preview": [{k: v for k, v in row.items() if k not in {"stream_obj", "pathway_obj"}} for row in valid], "errors": [], "ready": True, "committed": True, "created": len(valid)}, status=201)
