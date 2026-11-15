from decimal import Decimal, ROUND_HALF_UP
from datetime import timedelta

from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from schools.models import (
    AcademicYear, Enrollment, Exam, ExamResult, LevelResult, PublishedReportArtifact,
    Student, SubjectRegistration,
)
from .models import (
    BillingAuditLog, BillingConfiguration, BillingProfile, BillingTrialCycle,
    BillingTrialEvidence, PopulationSnapshot,
)

CENT = Decimal("0.01")


def config():
    return BillingConfiguration.objects.get_or_create(pk=1)[0]


def active_population(school_id):
    """Count unique active learners enrolled in the latest active school year."""
    year = AcademicYear.objects.filter(school_id=school_id, is_active=True).order_by("-start_date", "-pk").first()
    if year is None:
        return 0, None
    count = Student.objects.filter(
        school_id=school_id, status="active",
        enrollment__academic_year_id=year.pk, enrollment__is_active=True,
    ).values("pk").distinct().count()
    return count, year


def price_table(student_count, cfg=None):
    cfg = cfg or config()
    count = max(0, int(student_count))
    term = max(cfg.term_minimum_kes, Decimal(count) * cfg.per_student_term_kes).quantize(CENT, rounding=ROUND_HALF_UP)
    annual = (term * cfg.terms_per_year * (Decimal("1") - cfg.annual_discount_percent / Decimal("100"))).quantize(CENT, rounding=ROUND_HALF_UP)
    perpetual = (annual * cfg.perpetual_annual_multiplier).quantize(CENT, rounding=ROUND_HALF_UP)
    cloud_service = (annual * cfg.cloud_service_percent / Decimal("100")).quantize(CENT, rounding=ROUND_HALF_UP)
    school_maintenance = None
    if cfg.school_hosted_maintenance_percent is not None:
        school_maintenance = (annual * cfg.school_hosted_maintenance_percent / Decimal("100")).quantize(CENT, rounding=ROUND_HALF_UP)
    return {"termly_kes": term, "annual_kes": annual, "perpetual_kes": perpetual,
            "cloud_service_annual_kes": cloud_service,
            "school_maintenance_annual_kes": school_maintenance,
            "student_count": count}


def school_profile(school_id):
    # Existing Marian tenants are deliberately unconfigured until an owner maps
    # them; do not silently grant a new-school trial by upgrading this code.
    profile, _ = BillingProfile.objects.get_or_create(
        school_id=school_id,
        defaults={"access_type": "trial", "status": "unconfigured"},
    )
    return profile


def effective_status(profile):
    """Compute expiry on every request so a delayed job cannot grant access."""
    now = timezone.now()
    if profile.status == "subscription_active" and not profile.school.platform_subscriptions.filter(status="active", ends_at__gt=now).exists():
        return "subscription_expired"
    if profile.status == "licence_active":
        licence = profile.school.perpetual_licences.filter(status="active", deployment_type="cloud").order_by("-issued_at").first()
        if licence and licence.service_until and licence.service_until <= now:
            return "service_expired"
    return profile.status


def record_audit(*, actor, action, school=None, obj=None, details=None):
    return BillingAuditLog.objects.create(
        actor=actor, school=school, action=action,
        object_type=obj.__class__.__name__ if obj is not None else "",
        object_id=str(obj.pk) if obj is not None else "",
        details=details or {},
    )


def active_trial_cycle(school_id):
    return BillingTrialCycle.objects.filter(school_id=school_id, status="in_progress").select_related("term__academic_year").order_by("started_at", "pk").first()


def can_start_exam_cycle(school_id, term, assessment_type):
    """Return (allowed, detail). No calendar timer is used for a free trial."""
    profile = school_profile(school_id)
    status = effective_status(profile)
    cfg = config()
    if status in {"suspended", "payment_pending"}:
        return False, "Billing access is suspended or payment is pending. Contact Marian support or your school administrator."
    if status == "trial_completed":
        return False, "Your free trial has completed its first genuine examination cycle. Subscribe or purchase a licence before starting another examination cycle."
    if status in {"subscription_expired", "service_expired"} and cfg.post_expiry_policy_approved and cfg.post_expiry_policy != "unrestricted":
        return False, "This billing service has expired. Historical records remain available; renew or contact support before starting a new examination cycle."
    if status != "trial_active":
        return True, ""
    cycle = active_trial_cycle(school_id)
    if cycle and (cycle.term_id != term.pk or cycle.assessment_type != assessment_type):
        return False, "Complete the examination cycle already in progress, or contact support for help. The trial has no calendar expiry."
    return True, ""


def can_write_existing_exam(exam):
    """A trial may write only into its already-started first cycle."""
    profile = school_profile(exam.school_id)
    status = effective_status(profile)
    if status in {"suspended", "payment_pending", "trial_completed"}:
        return False, "This account cannot make further examination changes under its current billing status. Historical records remain preserved."
    if status == "trial_active":
        cycle = active_trial_cycle(exam.school_id)
        if cycle and (cycle.term_id != exam.term_id or cycle.assessment_type != exam.assessment_type):
            return False, "Start or continue the school’s first trial examination cycle. Contact support if you need help."
    cfg = config()
    if status in {"subscription_expired", "service_expired"} and cfg.post_expiry_policy_approved and cfg.post_expiry_policy != "unrestricted":
        return False, "This billing service has expired. Historical records remain available; renew or contact support before changing exam records."
    return True, ""


def can_write_trial_period(school_id, term, assessment_type):
    profile = school_profile(school_id)
    status = effective_status(profile)
    if status in {"suspended", "payment_pending", "trial_completed"}:
        return False, "This account cannot make further examination changes under its current billing status. Historical records remain preserved."
    if status == "trial_active":
        cycle = active_trial_cycle(school_id)
        if cycle and (cycle.term_id != term.pk or cycle.assessment_type != assessment_type):
            return False, "Start or continue the school’s first trial examination cycle. Contact support if you need help."
    cfg = config()
    if status in {"subscription_expired", "service_expired"} and cfg.post_expiry_policy_approved and cfg.post_expiry_policy != "unrestricted":
        return False, "This billing service has expired. Historical records remain available; renew or contact support before changing exam records."
    return True, ""


def start_trial_cycle(exam):
    profile = school_profile(exam.school_id)
    if profile.status != "trial_active":
        return None
    levels = list(Enrollment.objects.filter(
        academic_year_id=exam.term.academic_year_id, is_active=True,
        student__school_id=exam.school_id, student__status="active",
    ).values_list("class_level_id", flat=True).distinct())
    if not levels:
        return None
    cycle, created = BillingTrialCycle.objects.get_or_create(
        school_id=exam.school_id, term_id=exam.term_id,
        assessment_type=exam.assessment_type,
        defaults={"expected_class_level_ids": sorted(set(levels))},
    )
    if not created:
        merged = sorted(set(cycle.expected_class_level_ids or []) | set(levels))
        if merged != cycle.expected_class_level_ids:
            cycle.expected_class_level_ids = merged
            cycle.save(update_fields=["expected_class_level_ids"])
    record_evidence(cycle, exam, "exam_created", details={"class_level_id": exam.class_level_id})
    return cycle


def record_evidence(cycle, exam, kind, student=None, details=None):
    key = f"{cycle.pk}:{exam.pk}:{kind}:{student.pk if student else 0}"
    row, _ = BillingTrialEvidence.objects.get_or_create(
        evidence_key=key,
        defaults={"school_id": cycle.school_id, "cycle": cycle, "exam": exam,
                  "kind": kind, "student": student, "details": details or {}},
    )
    return row


def _exam_genuine_and_cohort(exam):
    """Re-check server-side that a published exam has marks for its eligible cohort."""
    if exam.status != "published":
        return False, set(), "Exam is not published."
    student_ids = set(Enrollment.objects.filter(
        academic_year_id=exam.term.academic_year_id, class_level_id=exam.class_level_id,
        is_active=True, student__school_id=exam.school_id, student__status="active",
    ).values_list("student_id", flat=True).distinct())
    if not student_ids:
        return False, set(), "The examination has no active enrolled cohort."
    registrations = set(SubjectRegistration.objects.filter(
        academic_year_id=exam.term.academic_year_id,
        student_id__in=student_ids, subject__school_id=exam.school_id,
    ).values_list("student_id", "subject_id"))
    if not registrations:
        return False, set(), "No eligible learner/subject registrations were included."
    numeric = set(ExamResult.objects.filter(exam=exam).values_list("student_id", flat=True))
    if numeric:
        if not student_ids.issubset(numeric):
            return False, set(), "Published results do not cover every active eligible learner."
        # Exam publication rejects empty/unapproved marks; additionally verify
        # materialized subject scores exist for each eligible result.
        rows = ExamResult.objects.filter(exam=exam, student_id__in=student_ids).values_list("student_id", "subject_scores")
        seen = {sid for sid, scores in rows if isinstance(scores, dict) and scores}
        if not student_ids.issubset(seen):
            return False, set(), "At least one eligible learner has no genuine scored result."
        return True, student_ids, "numeric"
    # CBC achievement-only publication stores locked LevelResult rows rather
    # than numeric ExamResult. Require every registered learner/subject pair.
    locked_pairs = set(LevelResult.objects.filter(
        student_id__in=student_ids,
        academic_year_id=exam.term.academic_year_id, term_id=exam.term_id,
        assessment_type=exam.assessment_type, status="locked",
        subject_id__in={subject_id for _, subject_id in registrations},
    ).values_list("student_id", "subject_id"))
    if not registrations.issubset(locked_pairs):
        return False, set(), "Approved achievement levels do not cover every eligible learner and registered subject."
    return True, student_ids, "achievement_levels"


def cycle_progress(cycle):
    levels = sorted(set(cycle.expected_class_level_ids or []))
    result = {"status": cycle.status, "term": cycle.term.name,
              "academic_year": cycle.term.academic_year.name,
              "assessment_type": cycle.assessment_type,
              "classes_expected": len(levels), "classes_published": 0,
              "analytics_generated": 0, "reports_generated": 0,
              "reports_expected": 0, "complete": False, "classes": []}
    if not levels:
        return result
    for level_id in levels:
        exam = Exam.objects.filter(school_id=cycle.school_id, term_id=cycle.term_id,
                                   assessment_type=cycle.assessment_type,
                                   class_level_id=level_id).first()
        row = {"class_level_id": level_id, "exam_id": exam.pk if exam else None,
               "published": False, "genuine_marks": False, "analytics": False,
               "reports_expected": 0, "reports_generated": 0}
        if exam:
            row["published"] = exam.status == "published"
            genuine, cohort, mode = _exam_genuine_and_cohort(exam) if exam.status == "published" else (False, set(), "")
            row["genuine_marks"] = genuine
            if genuine:
                row["result_mode"] = mode
                result["classes_published"] += 1
                row["reports_expected"] = len(cohort)
                result["reports_expected"] += len(cohort)
                row["analytics"] = cycle.evidence.filter(exam=exam, kind="analytics_generated").exists()
                if row["analytics"]:
                    result["analytics_generated"] += 1
                issued_ids = set(PublishedReportArtifact.objects.filter(
                    school_id=cycle.school_id, exam=exam, student_id__in=cohort,
                ).values_list("student_id", flat=True).distinct())
                row["reports_generated"] = len(issued_ids)
                result["reports_generated"] += len(issued_ids)
            else:
                row["reason"] = mode
        result["classes"].append(row)
    result["complete"] = bool(levels) and all(
        row["published"] and row["genuine_marks"] and row["analytics"]
        and row["reports_expected"] > 0
        and row["reports_generated"] >= row["reports_expected"]
        for row in result["classes"]
    )
    return result


def maybe_complete_trial(cycle):
    progress = cycle_progress(cycle)
    if not progress["complete"] or cycle.status != "in_progress":
        return False
    with transaction.atomic():
        locked = BillingTrialCycle.objects.select_for_update().get(pk=cycle.pk)
        if locked.status != "in_progress":
            return False
        locked.status = "completed"
        locked.completed_at = timezone.now()
        locked.completion_summary = progress
        locked.save(update_fields=["status", "completed_at", "completion_summary"])
        profile = BillingProfile.objects.select_for_update().filter(school_id=cycle.school_id).first()
        if profile and profile.status == "trial_active":
            profile.status = "trial_completed"
            profile.trial_completed_at = timezone.now()
            profile.save(update_fields=["status", "trial_completed_at", "updated_at"])
            record_audit(actor=None, action="trial_completed", school=cycle.school,
                         details={"cycle_id": cycle.pk, "term_id": cycle.term_id,
                                  "assessment_type": cycle.assessment_type})
    return True


def record_exam_published(exam):
    cycle = active_trial_cycle(exam.school_id)
    # Recover if the non-blocking exam-created evidence hook could not persist
    # the first cycle. Publication is another durable, real exam lifecycle event.
    if cycle is None:
        cycle = start_trial_cycle(exam)
    if cycle and cycle.term_id == exam.term_id and cycle.assessment_type == exam.assessment_type:
        record_evidence(cycle, exam, "exam_published")
        maybe_complete_trial(cycle)


def record_analytics_generated(exam):
    cycle = active_trial_cycle(exam.school_id)
    if not cycle or cycle.term_id != exam.term_id or cycle.assessment_type != exam.assessment_type:
        return
    genuine, _cohort, mode = _exam_genuine_and_cohort(exam)
    if genuine:
        record_evidence(cycle, exam, "analytics_generated", details={"result_mode": mode})
        maybe_complete_trial(cycle)


def record_report_generated(exam, student):
    cycle = active_trial_cycle(exam.school_id)
    if not cycle or cycle.term_id != exam.term_id or cycle.assessment_type != exam.assessment_type:
        return
    genuine, cohort, mode = _exam_genuine_and_cohort(exam)
    if genuine and student.pk in cohort:
        record_evidence(cycle, exam, "report_generated", student=student,
                        details={"result_mode": mode})
        maybe_complete_trial(cycle)


def snapshot_population(school_id, reason, invoice=None):
    count, year = active_population(school_id)
    profile = school_profile(school_id)
    snap = PopulationSnapshot.objects.create(
        school_id=school_id, academic_year=year, active_students=count,
        licensed_capacity=profile.licensed_capacity, reason=reason, invoice=invoice,
    )
    return snap, year


def expire_subscriptions():
    """Mark elapsed subscriptions expired without deleting school or academic data."""
    from .models import BillingSubscription, BillingProfile
    now = timezone.now()
    expired = BillingSubscription.objects.filter(status="active", ends_at__lte=now)
    school_ids = list(expired.values_list("school_id", flat=True).distinct())
    expired.update(status="expired")
    BillingProfile.objects.filter(school_id__in=school_ids, access_type="subscription", status="subscription_active").update(status="subscription_expired")
    return len(school_ids)
