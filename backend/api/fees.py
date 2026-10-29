from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Sum
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from api.fee_billing import (
    apply_structure, bill_student, carry_forward, drop_other_category_bills,
    parse_scope, previous_term, scope_data)

from schools.models import (
    AcademicYear, FeePayment, FeeStructure, MarkAuditLog,
    SchoolAdminProfile, StaffProfile, Student, StudentFee,
)


def _fee_school(request):
    if request.user.is_superuser:
        return None, None
    admin = SchoolAdminProfile.objects.filter(user=request.user).first()
    staff = StaffProfile.objects.filter(user=request.user, role="bursar").first()
    if admin:
        return admin.school_id, None
    if staff:
        return staff.school_id, None
    return None, Response({"detail": "Only admins and bursars can access fees."}, status=403)


def _money(value):
    return f"{Decimal(str(value or 0)):.2f}"


def _structure_data(x):
    return {**scope_data(x), "id": x.id, "name": x.name, "description": x.description,
            "amount": _money(x.amount), "due_date": x.due_date,
            "academic_year": x.academic_year_id, "is_active": x.is_active}


def _invoice_data(x):
    return {"id": x.id, "student": x.student_id,
            "student_name": str(x.student), "admission_number": x.student.admission_number,
            "fee_structure": x.fee_structure_id, "fee_name": x.fee_structure.name,
            "amount_due": _money(x.amount_due), "amount_paid": _money(x.amount_paid),
            "balance": _money(x.balance), "status": x.status,
            "due_date": x.fee_structure.due_date, "notes": x.notes}


def _payment_data(x):
    return {"id": x.id, "student_fee": x.student_fee_id, "student_name": str(x.student_fee.student),
            "amount": _money(x.amount), "method": x.method, "reference": x.reference,
            "paid_at": x.paid_at, "received_by": x.received_by.username if x.received_by else "",
            "notes": x.notes}


def _amt(raw):
    try:
        v = Decimal(str(raw).strip())
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Enter a valid amount.")
    if not v.is_finite() or v < 0:
        raise ValueError("Amount cannot be negative.")
    if v != v.quantize(Decimal("0.01")):
        raise ValueError("Use at most 2 decimal places.")
    return v


def _parse_amount(raw):
    try:
        v = Decimal(str(raw).strip())
    except (InvalidOperation, ValueError, TypeError):
        return None, "Enter a valid payment amount."
    if not v.is_finite() or v <= 0:
        return None, "Payment must be greater than zero."
    if v != v.quantize(Decimal("0.01")):
        return None, "Use at most 2 decimal places."
    return v, None


def _audit(request, invoice, action, details=None):
    MarkAuditLog.objects.create(school_id=invoice.student.school_id, user=request.user,
                                action=action, details=details or {})


@api_view(["GET"])
def fee_summary(request):
    school_id, error = _fee_school(request)
    if error:
        return error
    qs = StudentFee.objects.all()
    if school_id is not None:
        qs = qs.filter(student__school_id=school_id)
    qs = qs.exclude(status="waived")
    totals = qs.aggregate(due=Sum("amount_due"), paid=Sum("amount_paid"))
    due = totals["due"] or Decimal("0.00")
    paid = totals["paid"] or Decimal("0.00")
    overdue = qs.filter(fee_structure__due_date__lt=timezone.localdate()).exclude(
        status__in=["paid", "waived"])
    return Response({"invoices": qs.count(), "students": qs.values("student_id").distinct().count(),
                     "amount_due": _money(due), "amount_paid": _money(paid),
                     "balance": _money(max(due - paid, 0)), "overdue": overdue.count(),
                     "overdue_amount": _money(overdue.aggregate(x=Sum(ExpressionWrapper(F("amount_due") - F("amount_paid"), output_field=DecimalField(max_digits=12, decimal_places=2))))["x"] or 0)})


@api_view(["GET", "POST"])
def fee_structures(request):
    school_id, error = _fee_school(request)
    if error:
        return error
    if request.method == "GET":
        qs = FeeStructure.objects.select_related("academic_year")
        if school_id is not None:
            qs = qs.filter(school_id=school_id)
        return Response([_structure_data(x) for x in qs])
    data = request.data
    year = AcademicYear.objects.filter(id=data.get("academic_year")).first()
    if not year or school_id is not None and year.school_id != school_id:
        return Response({"detail": "Academic year is not in your school."}, status=403)
    if not data.get("name", "").strip():
        return Response({"detail": "Fee name is required."}, status=400)
    scope, scope_error = parse_scope(data, school_id or year.school_id, year)
    if scope_error:
        return Response({"detail": scope_error}, status=400)
    try:
        x = FeeStructure.objects.create(
            school_id=school_id or year.school_id, academic_year=year,
            name=data["name"].strip(), description=data.get("description", ""),
            amount=_amt(data.get("amount", "0")), due_date=data.get("due_date") or None,
        )
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=400)
    except Exception:
        return Response({"detail": "Could not save. Check the details and try again."}, status=400)
    for key, value in scope.items():
        setattr(x, key, value)
    x.save()
    out = _structure_data(x)
    out.update(apply_structure(x))
    return Response(out, status=201)


@api_view(["PATCH", "PUT"])
def fee_structure_detail(request, pk):
    """Edit a fee item (amount, category, term, grades) and re-bill learners."""
    school_id, error = _fee_school(request)
    if error:
        return error
    x = FeeStructure.objects.filter(pk=pk).first()
    if x is None or (school_id is not None and x.school_id != school_id):
        return Response({"detail": "Fee item not found."}, status=404)
    data = request.data
    merged = {
        "term": data.get("term", x.term_id),
        "category": data.get("category", x.category),
        "from_grade": data.get("from_grade", x.from_grade),
        "to_grade": data.get("to_grade", x.to_grade),
    }
    scope, scope_error = parse_scope(merged, x.school_id, x.academic_year)
    if scope_error:
        return Response({"detail": scope_error}, status=400)
    if "name" in data and str(data["name"]).strip():
        x.name = str(data["name"]).strip()
    if "amount" in data:
        try:
            x.amount = _amt(data["amount"])
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
    if "due_date" in data:
        x.due_date = data["due_date"] or None
    for key, value in scope.items():
        setattr(x, key, value)
    x.save()
    out = _structure_data(x)
    out.update(apply_structure(x))
    return Response(out)


@api_view(["GET", "POST"])
def fee_invoices(request):
    school_id, error = _fee_school(request)
    if error:
        return error
    if request.method == "GET":
        qs = StudentFee.objects.select_related("student", "fee_structure")
        if school_id is not None:
            qs = qs.filter(student__school_id=school_id)
        status = request.GET.get("status")
        if status:
            qs = qs.filter(status=status)
        return Response([_invoice_data(x) for x in qs[:500]])
    data = request.data
    student = Student.objects.filter(id=data.get("student")).first()
    structure = FeeStructure.objects.filter(id=data.get("fee_structure")).first()
    if not student or not structure or student.school_id != structure.school_id:
        return Response({"detail": "Student and fee structure must be valid."}, status=400)
    if school_id is not None and student.school_id != school_id:
        return Response({"detail": "Student is not in your school."}, status=403)
    try:
        x = StudentFee.objects.create(student=student, fee_structure=structure,
                                      amount_due=_amt(data.get("amount_due", structure.amount)),
                                      notes=data.get("notes", ""))
        _audit(request, x, "fee_assigned", {"amount_due": _money(x.amount_due)})
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=400)
    except Exception:
        return Response({"detail": "Could not save. Check the details and try again."}, status=400)
    return Response(_invoice_data(x), status=201)


@api_view(["POST"])
def fee_payment(request):
    school_id, error = _fee_school(request)
    if error:
        return error
    amount, amount_error = _parse_amount(request.data.get("amount"))
    if amount_error:
        return Response({"detail": amount_error}, status=400)
    reference = str(request.data.get("reference", "") or "").strip()[:80]
    try:
        with transaction.atomic():
            invoice = StudentFee.objects.select_for_update().select_related(
                "student", "fee_structure").get(pk=request.data.get("student_fee"))
            if school_id is not None and invoice.student.school_id != school_id:
                return Response({"detail": "Invoice is not in your school."}, status=403)
            if invoice.status in ["paid", "waived"]:
                return Response({"detail": "This invoice cannot receive another payment."}, status=400)
            balance = invoice.amount_due - invoice.amount_paid
            if amount > balance:
                return Response({"detail": "Payment must be greater than zero and not exceed the balance."}, status=400)
            if reference and FeePayment.objects.filter(
                    student_fee__student__school_id=invoice.student.school_id,
                    reference__iexact=reference).exists():
                return Response({"detail": "A payment with this reference is already recorded."}, status=409)
            payment = FeePayment.objects.create(
                student_fee=invoice, amount=amount, method=request.data.get("method", "cash"),
                reference=reference, notes=request.data.get("notes", ""),
                received_by=request.user)
            invoice.amount_paid += amount
            invoice.status = "paid" if invoice.amount_paid >= invoice.amount_due else "partial"
            invoice.save(update_fields=["amount_paid", "status", "updated_at"])
            _audit(request, invoice, "fee_payment", {"amount": _money(amount), "payment_id": payment.id})
    except (StudentFee.DoesNotExist, ValueError, TypeError):
        return Response({"detail": "Invoice not found."}, status=404)
    data = _invoice_data(invoice)
    data['payment_id'] = payment.id
    return Response(data, status=201)


@api_view(["GET"])
def fee_payments(request):
    school_id, error = _fee_school(request)
    if error:
        return error
    qs = FeePayment.objects.select_related("student_fee__student", "received_by")
    if school_id is not None:
        qs = qs.filter(student_fee__student__school_id=school_id)
    if request.GET.get("student_fee"):
        qs = qs.filter(student_fee_id=request.GET["student_fee"])
    return Response([_payment_data(x) for x in qs[:500]])


@api_view(["POST"])
def fee_waive(request, pk):
    school_id, error = _fee_school(request)
    if error:
        return error
    try:
        with transaction.atomic():
            invoice = StudentFee.objects.select_for_update().select_related(
                "student", "fee_structure").get(pk=pk)
            if school_id is not None and invoice.student.school_id != school_id:
                return Response({"detail": "Invoice is not in your school."}, status=403)
            if invoice.status == "paid":
                return Response({"detail": "A paid invoice cannot be waived."}, status=400)
            invoice.status = "waived"
            invoice.save(update_fields=["status", "updated_at"])
            _audit(request, invoice, "fee_waived", {"reason": request.data.get("reason", "")})
    except StudentFee.DoesNotExist:
        return Response({"detail": "Invoice not found."}, status=404)
    return Response(_invoice_data(invoice))


@api_view(["GET"])
def fee_report(request):
    school_id, error = _fee_school(request)
    if error:
        return error
    qs = StudentFee.objects.select_related("fee_structure")
    if school_id is not None:
        qs = qs.filter(student__school_id=school_id)
    rows = []
    for item in qs.values("fee_structure_id", "fee_structure__name").annotate(
        invoices=Count("id"), due=Sum("amount_due"), paid=Sum("amount_paid")):
        due, paid = item["due"] or 0, item["paid"] or 0
        rows.append({"fee_structure": item["fee_structure_id"], "name": item["fee_structure__name"],
                     "invoices": item["invoices"], "due": _money(due), "paid": _money(paid),
                     "balance": _money(max(due - paid, 0))})
    return Response(rows)


@api_view(["GET"])
def fee_receipt(request, pk):
    """Read-only receipt data for one payment. Never changes money."""
    school_id, error = _fee_school(request)
    if error:
        return error
    qs = FeePayment.objects.select_related(
        "student_fee__student__school", "student_fee__fee_structure__academic_year", "received_by")
    if school_id is not None:
        qs = qs.filter(student_fee__student__school_id=school_id)
    payment = qs.filter(pk=pk).first()
    if payment is None:
        return Response({"detail": "Receipt not found."}, status=404)
    fee = payment.student_fee
    student = fee.student
    school = student.school
    earlier = sum(
        (x.amount for x in FeePayment.objects.filter(student_fee=fee, id__lt=payment.id)),
        Decimal("0"))
    all_paid = sum((x.amount for x in FeePayment.objects.filter(student_fee=fee)), Decimal("0"))
    verified = fee.status != "waived" and all_paid == fee.amount_paid
    previous = fee.amount_due - earlier if verified else None
    after = previous - payment.amount if verified else None
    cashier = ""
    if payment.received_by:
        cashier = payment.received_by.get_full_name() or payment.received_by.username
    return Response({
        "receipt_number": f"RCPT-{school.code}-{payment.id:06d}",
        "school": {
            "name": school.name, "motto": school.motto, "location": school.location,
            "county": school.county, "sub_county": school.sub_county,
            "phone": school.phone, "email": school.email,
            "logo": school.logo.url if school.logo else "", "currency": school.currency,
        },
        "student": {"name": str(student), "admission_number": student.admission_number},
        "fee": {
            "name": fee.fee_structure.name,
            "academic_year": str(fee.fee_structure.academic_year),
            "amount_due": _money(fee.amount_due), "status": fee.status,
            "balance_brought_forward": _money(fee.balance_brought_forward),
            "category": student.fee_category,
        },
        "payment": {
            "amount": _money(payment.amount), "method": payment.method,
            "method_display": payment.get_method_display(), "reference": payment.reference,
            "paid_at": payment.paid_at, "received_by": cashier, "notes": payment.notes,
        },
        "balances_verified": verified,
        "status_at_payment": ("paid" if after <= 0 else "partial") if verified else None,
        "previous_balance": _money(previous) if verified else None,
        "balance_after": _money(after) if verified else None,
    })


@api_view(["POST"])
def student_categories(request):
    """Set day/boarder for many learners at once, then fix their bills."""
    from schools.models import Student
    school_id, error = _fee_school(request)
    if error:
        return error
    category = str(request.data.get("category", "")).strip().lower()
    if category not in ("day", "boarder"):
        return Response({"detail": "Category must be day or boarder."}, status=400)
    try:
        ids = [int(i) for i in (request.data.get("students") or [])]
    except (TypeError, ValueError):
        return Response({"detail": "Students must be a list of ids."}, status=400)
    if not ids:
        return Response({"detail": "Pick at least one learner."}, status=400)
    qs = Student.objects.filter(id__in=ids)
    if school_id is not None:
        qs = qs.filter(school_id=school_id)
    changed = removed = created = 0
    for st in qs:
        if st.fee_category != category:
            st.fee_category = category
            st.save(update_fields=["fee_category"])
            removed += drop_other_category_bills(st)
            changed += 1
        created += bill_student(st)
    return Response({"students_changed": changed, "bills_removed": removed, "bills_created": created})


@api_view(["POST"])
def carry_forward_arrears(request):
    """Carry unpaid balances of the previous term into the chosen term."""
    from schools.models import Student, Term
    school_id, error = _fee_school(request)
    if error:
        return error
    term = Term.objects.select_related("academic_year").filter(
        pk=request.data.get("term") or 0).first()
    if term is None or (school_id is not None and term.academic_year.school_id != school_id):
        return Response({"detail": "Term not found."}, status=404)
    prev = previous_term(term)
    if prev is None:
        return Response({"detail": "There is no earlier term to carry from."}, status=400)
    if prev.end_date >= timezone.localdate():
        return Response({"detail": "The previous term has not ended yet."}, status=400)
    students, moved = 0, Decimal("0")
    for st in Student.objects.filter(fees__fee_structure__term=term).distinct():
        m = carry_forward(st, term)
        if m:
            students += 1
            moved += m
    return Response({"students_carried": students, "amount_carried": _money(moved)})


def _decimal(value):
    try:
        d = Decimal(str(value).strip())
        if not d.is_finite() or abs(d) > Decimal("999999999"):
            return None
        return d.quantize(Decimal("0.01"))
    except Exception:
        return None


def _adjust_payload(invoice):
    rows = [{
        "id": a.id, "when": a.created_at.isoformat(),
        "by": (a.made_by.get_full_name() or a.made_by.username) if a.made_by else "",
        "from": _money(a.old_amount_due), "to": _money(a.new_amount_due),
        "reason": a.reason,
    } for a in invoice.adjustments.select_related("made_by").order_by("-id")]
    return {
        "invoice": {
            "id": invoice.id, "student_name": str(invoice.student),
            "fee_name": invoice.fee_structure.name,
            "amount_due": _money(invoice.amount_due),
            "amount_paid": _money(invoice.amount_paid),
            "balance": _money(invoice.balance),
            "balance_brought_forward": _money(invoice.balance_brought_forward),
            "status": invoice.status,
        },
        "history": rows,
    }


@api_view(["GET", "POST"])
def fee_adjust(request, pk):
    """See or change one learner's bill. Every change needs a reason and is recorded."""
    from schools.models import FeeAdjustment
    school_id, error = _fee_school(request)
    if error:
        return error
    with transaction.atomic():
        invoice = (StudentFee.objects.select_for_update()
                   .select_related("student", "fee_structure").filter(pk=pk).first())
        if invoice is None or (school_id is not None and invoice.student.school_id != school_id):
            return Response({"detail": "Invoice not found."}, status=404)
        if request.method == "POST":
            reason = str(request.data.get("reason", "")).strip()[:200]
            if len(reason) < 3:
                return Response({"detail": "Please give a short reason for the change."}, status=400)
            if invoice.status == "waived":
                return Response({"detail": "A waived bill cannot be adjusted."}, status=400)
            mode = request.data.get("mode", "set")
            if mode not in ("set", "change"):
                return Response({"detail": "Choose set or change."}, status=400)
            value = _decimal(request.data.get("value"))
            if value is None:
                return Response({"detail": "Enter a valid amount."}, status=400)
            new_due = value if mode == "set" else invoice.amount_due + value
            if new_due < 0:
                return Response({"detail": "Amount due cannot be negative."}, status=400)
            if new_due < invoice.amount_paid:
                return Response({"detail": f"Amount due cannot be less than the KES {_money(invoice.amount_paid)} already paid."}, status=400)
            if new_due == invoice.amount_due:
                return Response({"detail": "That is already the amount due."}, status=400)
            old = invoice.amount_due
            invoice.amount_due = new_due
            if invoice.amount_paid >= new_due:
                invoice.status = "paid"
            elif invoice.amount_paid > 0:
                invoice.status = "partial"
            else:
                invoice.status = "pending"
            invoice.manually_adjusted = True
            invoice.save(update_fields=["amount_due", "status", "manually_adjusted", "updated_at"])
            FeeAdjustment.objects.create(
                student_fee=invoice, old_amount_due=old, new_amount_due=new_due,
                reason=reason, made_by=request.user)
            _audit(request, invoice, "fee_adjusted",
                   {"from": _money(old), "to": _money(new_due), "reason": reason})
        return Response(_adjust_payload(invoice))


@api_view(["GET"])
def fee_statement(request, pk):
    """Balance statement for one learner. Works at any time, paid up or not."""
    from schools.models import FeeAdjustment, Student
    school_id, error = _fee_school(request)
    if error:
        return error
    student = Student.objects.select_related("school").filter(pk=pk).first()
    if student is None or (school_id is not None and student.school_id != school_id):
        return Response({"detail": "Learner not found."}, status=404)
    school = student.school
    fees = (StudentFee.objects.filter(student=student)
            .select_related("fee_structure__academic_year", "fee_structure__term")
            .order_by("fee_structure__academic_year__start_date",
                      "fee_structure__term__start_date", "id"))
    bills, billed, paid, balance = [], Decimal("0"), Decimal("0"), Decimal("0")
    for f in fees:
        counted = f.status != "waived"
        owed = f.balance if counted else Decimal("0")
        if counted:
            billed += f.amount_due
            paid += f.amount_paid
            balance += owed
        fs = f.fee_structure
        bills.append({
            "fee": fs.name, "term": fs.term.name if fs.term_id else "",
            "year": str(fs.academic_year),
            "amount_due": _money(f.amount_due),
            "balance_brought_forward": _money(f.balance_brought_forward),
            "carried_out": _money(f.carried_out),
            "paid": _money(f.amount_paid), "balance": _money(owed),
            "status": f.status,
        })
    payments = []
    for p in (FeePayment.objects.filter(student_fee__student=student)
              .select_related("student_fee__fee_structure").order_by("-id")):
        when = getattr(p, "paid_at", None) or getattr(p, "created_at", None)
        payments.append({
            "receipt_number": f"RCPT-{school.code}-{p.id:06d}",
            "date": when.isoformat() if when else "",
            "fee": p.student_fee.fee_structure.name,
            "amount": _money(p.amount), "method": p.method,
            "reference": p.reference,
        })
    changes = [{
        "when": a.created_at.isoformat(), "fee": a.student_fee.fee_structure.name,
        "from": _money(a.old_amount_due), "to": _money(a.new_amount_due),
        "reason": a.reason,
    } for a in FeeAdjustment.objects.filter(student_fee__student=student)
        .select_related("student_fee__fee_structure")]
    return Response({
        "as_of": timezone.localdate().isoformat(),
        "school": {
            "name": school.name, "motto": school.motto, "location": school.location,
            "county": school.county, "sub_county": school.sub_county,
            "phone": school.phone, "email": school.email,
            "logo": school.logo.url if school.logo else "",
            "currency": school.currency,
        },
        "student": {
            "name": str(student), "admission_number": student.admission_number,
            "category": student.fee_category,
        },
        "bills": bills, "payments": payments, "adjustments": changes,
        "totals": {"billed": _money(billed), "paid": _money(paid), "balance": _money(balance)},
    })


@api_view(["GET"])
def fee_years(request):
    from api.serializers import AcademicYearSerializer
    from schools.models import AcademicYear
    school_id, error = _fee_school(request)
    if error:
        return error
    qs = AcademicYear.objects.all()
    if school_id is not None:
        qs = qs.filter(school_id=school_id)
    return Response(AcademicYearSerializer(qs.order_by("-start_date"), many=True).data)


@api_view(["GET"])
def fee_terms(request):
    from api.serializers import TermSerializer
    from schools.models import Term
    school_id, error = _fee_school(request)
    if error:
        return error
    qs = Term.objects.all()
    if school_id is not None:
        qs = qs.filter(academic_year__school_id=school_id)
    return Response(TermSerializer(qs.order_by("start_date"), many=True).data)


@api_view(["GET"])
def fee_students(request):
    from api.serializers import StudentSerializer
    from schools.models import Student
    school_id, error = _fee_school(request)
    if error:
        return error
    qs = Student.objects.all()
    if school_id is not None:
        qs = qs.filter(school_id=school_id)
    return Response(StudentSerializer(qs.order_by("last_name", "first_name"), many=True).data)
