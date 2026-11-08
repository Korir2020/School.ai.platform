from django.db import transaction
from django.db.models import Exists, F, OuterRef
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.response import Response

from schools.models import (
    AcademicYear, CurriculumPathway, Enrollment, Exam, MarkAuditLog, Performance,
    SchoolAdminProfile, Student, Subject, SubjectRegistration,
    TeacherAssignment,
)
from .pagination import paginated_response
from .senior_rules import is_cbc_senior, pathway_matches_class, subject_definition_problem
from .views import _scope


class SubjectRegistrationSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubjectRegistration
        fields = ("id", "student", "academic_year", "subject", "category",
                  "registered_by", "created_at", "updated_at")
        read_only_fields = ("registered_by", "created_at", "updated_at")


def _is_admin(user):
    return user.is_superuser or SchoolAdminProfile.objects.filter(user=user).exists()


def _positive_int(value):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


@api_view(["GET", "POST"])
def subject_registration_collection(request):
    school_id, error = _scope(request)
    if error:
        return error

    if request.method == "GET":
        rows = SubjectRegistration.objects.select_related(
            "student", "academic_year", "subject")
        if school_id is not None:
            rows = rows.filter(student__school_id=school_id)
        year_id = request.query_params.get("academic_year")
        student_id = request.query_params.get("student")
        subject_id = request.query_params.get("subject")
        if year_id:
            if not _positive_int(year_id):
                return Response({"detail": "Invalid academic_year filter."}, status=400)
            rows = rows.filter(academic_year_id=int(year_id))
        if student_id:
            if not _positive_int(student_id):
                return Response({"detail": "Invalid student filter."}, status=400)
            rows = rows.filter(student_id=int(student_id))
        if subject_id:
            if not _positive_int(subject_id):
                return Response({"detail": "Invalid subject filter."}, status=400)
            rows = rows.filter(subject_id=int(subject_id))
        if not request.user.is_superuser and not SchoolAdminProfile.objects.filter(
            user=request.user,
        ).exists():
            assigned = TeacherAssignment.objects.filter(
                teacher__user=request.user,
                school_id=school_id,
                subject_id=OuterRef("subject_id"),
                stream_id=OuterRef("student__enrollment__stream_id"),
            )
            rows = rows.filter(
                student__enrollment__is_active=True,
                student__enrollment__academic_year_id=F("academic_year_id"),
            ).annotate(_assigned_stream=Exists(assigned)).filter(
                _assigned_stream=True,
            ).distinct()
        return paginated_response(request, rows, SubjectRegistrationSerializer)

    if not _is_admin(request.user):
        return Response({"detail": "Only school admins can update registrations."}, status=403)

    student_id = _positive_int(request.data.get("student"))
    year_id = _positive_int(request.data.get("academic_year"))
    items = request.data.get("subjects")
    if not student_id or not year_id or not isinstance(items, list):
        return Response({"detail": "student, academic_year, and a subjects list are required."}, status=400)
    if not items:
        return Response({"detail": "Register at least one subject for the learner."}, status=400)
    if len(items) > 100:
        return Response({"detail": "A learner may have at most 100 registered subjects."}, status=400)

    student = Student.objects.filter(pk=student_id).first()
    year = AcademicYear.objects.filter(pk=year_id).first()
    if student is None or year is None:
        return Response({"detail": "Student or academic year not found."}, status=404)
    if student.school_id != year.school_id:
        return Response({"detail": "Student and academic year must belong to the same school."}, status=400)
    if school_id is not None and student.school_id != school_id:
        return Response({"detail": "Records must belong to your school."}, status=403)
    enrollment = Enrollment.objects.filter(
        student=student, academic_year=year, is_active=True
    ).select_related("class_level__curriculum", "pathway").first()
    if enrollment is None:
        return Response({"detail": "The learner must have an active enrollment in this academic year."}, status=400)
    senior = is_cbc_senior(enrollment.class_level)
    requested_pathway = enrollment.pathway
    raw_pathway = request.data.get("pathway")
    if senior:
        if raw_pathway not in (None, ""):
            pathway_id = _positive_int(raw_pathway)
            requested_pathway = CurriculumPathway.objects.filter(
                pk=pathway_id, is_active=True,
            ).first() if pathway_id else None
        if requested_pathway is None or not pathway_matches_class(requested_pathway, enrollment.class_level):
            return Response({"detail": "Choose an active CBC Senior pathway that applies to this grade."}, status=400)
    elif raw_pathway not in (None, ""):
        return Response({"detail": "Pathways apply only to CBC Senior Grades 10–12."}, status=400)

    subject_ids, categories = [], {}
    errors = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append({"index": index, "detail": "Each subject registration must be an object."})
            continue
        subject_id = _positive_int(item.get("subject"))
        category = item.get("category")
        if not subject_id:
            errors.append({"index": index, "detail": "A valid subject is required."})
            continue
        if subject_id in categories:
            errors.append({"index": index, "detail": "Duplicate subject registration."})
            continue
        if category not in {"compulsory", "optional"}:
            errors.append({"index": index, "detail": "Category must be compulsory or optional."})
            continue
        subject_ids.append(subject_id)
        categories[subject_id] = category
    if errors:
        return Response({"detail": "Invalid subject registrations.", "errors": errors}, status=400)

    subjects = list(Subject.objects.filter(
        pk__in=subject_ids, school_id=student.school_id, is_active=True
    ).select_related("definition").prefetch_related(
        "definition__class_levels", "definition__pathways"))
    by_id = {subject.id: subject for subject in subjects}
    missing = sorted(set(subject_ids) - set(by_id))
    if missing:
        return Response({"detail": "Subjects must be active and belong to the learner's school.",
                         "subject_ids": missing}, status=400)
    for subject in subjects:
        definition = subject.definition
        if senior:
            problem = subject_definition_problem(definition, enrollment.class_level, requested_pathway)
            if problem:
                return Response({"detail": problem}, status=400)
        elif definition and definition.class_levels.exists() and not definition.class_levels.filter(
            pk=enrollment.class_level_id
        ).exists():
            return Response({"detail": f"{subject.name} is not available for {enrollment.class_level.name}."}, status=400)

    with transaction.atomic():
        Student.objects.select_for_update().get(pk=student.pk)
        locked_enrollment = Enrollment.objects.select_for_update().select_related(
            "class_level__curriculum", "pathway").get(pk=enrollment.pk)
        if senior and not pathway_matches_class(requested_pathway, locked_enrollment.class_level):
            return Response({"detail": "The selected CBC Senior pathway is no longer active for this grade."}, status=409)
        pathway_changed = senior and locked_enrollment.pathway_id != requested_pathway.pk
        current = list(SubjectRegistration.objects.select_for_update().filter(
            student=student, academic_year=year))
        current_by_subject = {row.subject_id: row for row in current}
        wanted = set(subject_ids)
        current_ids = set(current_by_subject)
        category_changed = sorted(
            sid for sid in wanted & current_ids
            if categories[sid] != current_by_subject[sid].category
        )
        changed = wanted != current_ids or bool(category_changed) or pathway_changed
        enrolled_class_levels = Enrollment.objects.filter(
            student=student, academic_year=year,
        ).values("class_level_id")
        published = Exam.objects.filter(
            school_id=student.school_id, term__academic_year=year,
            class_level_id__in=enrolled_class_levels, status="published",
        ).exists()
        if published and changed:
            return Response({
                "detail": "Registrations are locked after a published exam for this academic year."
            }, status=409)
        removed = current_ids - wanted
        added = wanted - current_ids
        if added and Performance.objects.filter(
            student=student, academic_year=year, subject_id__in=added,
        ).exists():
            return Response({
                "detail": "A subject with existing marks cannot be added retroactively to the learner's registration."
            }, status=409)
        if removed and Performance.objects.filter(
            student=student, academic_year=year, subject_id__in=removed,
            status__in=["approved", "locked"],
        ).exists():
            return Response({
                "detail": "A subject with approved marks cannot be removed from the learner's registration."
            }, status=409)

        to_create, to_update = [], []
        for subject_id, category in categories.items():
            existing = current_by_subject.get(subject_id)
            if existing is None:
                to_create.append(SubjectRegistration(
                    student=student, academic_year=year, subject_id=subject_id,
                    category=category, registered_by=request.user,
                ))
            elif existing.category != category:
                existing.category = category
                existing.registered_by = request.user
                existing.updated_at = timezone.now()
                to_update.append(existing)
        if removed:
            SubjectRegistration.objects.filter(
                student=student, academic_year=year, subject_id__in=removed,
            ).delete()
        if to_update:
            SubjectRegistration.objects.bulk_update(to_update, ["category", "registered_by", "updated_at"])
        if to_create:
            SubjectRegistration.objects.bulk_create(to_create)
        if pathway_changed:
            locked_enrollment.pathway = requested_pathway
            locked_enrollment.save(update_fields=["pathway"])
        if changed:
            MarkAuditLog.objects.create(
                school_id=student.school_id, user=request.user,
                action="subject_registration_updated",
                details={
                    "student": student.id, "academic_year": year.id,
                    "added": sorted(added),
                    "removed": sorted(removed),
                    "category_changed": category_changed,
                    "pathway_from": locked_enrollment.pathway_id if not pathway_changed else enrollment.pathway_id,
                    "pathway_to": requested_pathway.pk if senior else None,
                },
            )
        result = SubjectRegistration.objects.filter(
            student=student, academic_year=year,
        ).select_related("subject").order_by("subject__name", "id")
        return Response({
            "student": student.id,
            "academic_year": year.id,
            "pathway": requested_pathway.pk if senior else None,
            "count": result.count(),
            "registrations": SubjectRegistrationSerializer(result, many=True).data,
        }, status=200)
