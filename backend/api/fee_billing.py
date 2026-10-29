from django.db import transaction

from schools.models import Enrollment, Student, StudentFee, Term

CATEGORIES = ("day", "boarder")


def _grade(raw, label):
    if raw in (None, ""):
        return None
    try:
        n = int(str(raw).strip())
    except ValueError:
        raise ValueError(f"{label} must be a whole number.")
    if n < 0 or n > 30:
        raise ValueError(f"{label} is not a valid grade.")
    return n


def parse_scope(data, school_id, year):
    """Return (scope dict, error text) from the request data."""
    scope = {"term": None, "category": "", "from_grade": None, "to_grade": None}
    term_id = data.get("term")
    if term_id not in (None, ""):
        term = Term.objects.filter(id=term_id, academic_year=year).first()
        if not term:
            return None, "Term is not in this academic year."
        scope["term"] = term
    category = (data.get("category") or "").strip().lower()
    if category in ("all", "everyone"):
        category = ""
    if category and category not in CATEGORIES:
        return None, "Category must be day, boarder or everyone."
    scope["category"] = category
    try:
        scope["from_grade"] = _grade(data.get("from_grade"), "From grade")
        scope["to_grade"] = _grade(data.get("to_grade"), "To grade")
    except ValueError as exc:
        return None, str(exc)
    a, b = scope["from_grade"], scope["to_grade"]
    if a is not None and b is not None and a > b:
        return None, "From grade cannot be higher than To grade."
    return scope, None


def scope_data(x):
    return {
        "term": x.term_id,
        "term_name": x.term.name if x.term_id else "",
        "category": x.category,
        "from_grade": x.from_grade,
        "to_grade": x.to_grade,
    }


def matching_students(s):
    qs = Student.objects.filter(school_id=s.school_id)
    if s.category:
        qs = qs.filter(fee_category=s.category)
    if s.from_grade is not None or s.to_grade is not None:
        en = Enrollment.objects.filter(
            academic_year_id=s.academic_year_id, is_active=True)
        if s.from_grade is not None:
            en = en.filter(class_level__level_number__gte=s.from_grade)
        if s.to_grade is not None:
            en = en.filter(class_level__level_number__lte=s.to_grade)
        qs = qs.filter(id__in=en.values("student_id"))
    return qs


@transaction.atomic
def apply_structure(s):
    """Bill every matching learner. Safe to run again: nobody is billed twice."""
    if not s.is_active:
        return {"students_billed": 0, "students_updated": 0}
    existing = {f.student_id: f
                for f in StudentFee.objects.filter(fee_structure=s)}
    new, updated = [], 0
    for sid in matching_students(s).values_list("id", flat=True):
        f = existing.get(sid)
        if f is None:
            new.append(StudentFee(student_id=sid, fee_structure=s,
                                  amount_due=s.amount))
        elif (f.amount_paid == 0 and f.status == "pending"
              and f.amount_due != s.amount + f.balance_brought_forward):
            f.amount_due = s.amount + f.balance_brought_forward
            f.save(update_fields=["amount_due", "updated_at"])
            updated += 1
    StudentFee.objects.bulk_create(new)
    if s.term_id:
        for st in matching_students(s):
            carry_forward(st, s.term)
    return {"students_billed": len(new), "students_updated": updated}


def bill_student(student):
    """Bill one learner for every matching fee item they are missing.
    Only creates missing bills; never changes or removes an existing one."""
    from schools.models import FeeStructure, StudentFee
    created = 0
    for s in FeeStructure.objects.filter(
            school_id=student.school_id, is_active=True,
            academic_year__is_active=True):
        if StudentFee.objects.filter(student=student, fee_structure=s).exists():
            continue
        if matching_students(s).filter(id=student.id).exists():
            StudentFee.objects.create(
                student=student, fee_structure=s, amount_due=s.amount)
            created += 1
            if s.term_id:
                carry_forward(student, s.term)
    return created


def drop_other_category_bills(student):
    """After a category change: remove bills for the other category that are
    still unpaid and untouched. Anything with a payment is kept."""
    from schools.models import StudentFee
    qs = (StudentFee.objects
          .filter(student=student, status="pending", amount_paid=0,
                  fee_structure__academic_year__is_active=True,
                  payments__isnull=True)
          .exclude(fee_structure__category="")
          .exclude(fee_structure__category=student.fee_category))
    ids = list(qs.values_list("id", flat=True))
    StudentFee.objects.filter(id__in=ids).delete()
    return len(ids)


def previous_term(term):
    from schools.models import Term
    if term is None or term.start_date is None:
        return None
    return (Term.objects
            .filter(academic_year__school_id=term.academic_year.school_id,
                    end_date__lt=term.start_date)
            .order_by("-end_date").first())


def carry_forward(student, term):
    """Move what a learner still owes from the previous term onto their first
    unpaid bill of `term`. Only runs once the previous term has ended.
    Safe to run again: carried bills end up fully paid, so nothing moves twice."""
    from decimal import Decimal
    from django.db import transaction
    from django.utils import timezone
    from schools.models import StudentFee
    prev = previous_term(term)
    if prev is None or prev.end_date >= timezone.localdate():
        return Decimal("0")
    moved = Decimal("0")
    with transaction.atomic():
        target = (StudentFee.objects.select_for_update()
                  .filter(student=student, fee_structure__term=term,
                          status__in=["pending", "partial"])
                  .order_by("id").first())
        if target is None:
            return Decimal("0")
        olds = (StudentFee.objects.select_for_update()
                .filter(student=student, fee_structure__term=prev,
                        status__in=["pending", "partial"]))
        for f in olds:
            owed = f.amount_due - f.amount_paid
            if owed <= 0:
                continue
            f.amount_due = f.amount_paid
            f.carried_out += owed
            f.status = "paid"
            f.save(update_fields=["amount_due", "carried_out", "status", "updated_at"])
            moved += owed
        if moved:
            target.amount_due += moved
            target.balance_brought_forward += moved
            target.save(update_fields=["amount_due", "balance_brought_forward", "updated_at"])
    return moved
