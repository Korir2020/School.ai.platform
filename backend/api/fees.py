from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Sum
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from api.fee_billing import apply_structure, parse_scope, scope_data

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
    return Response(_invoice_data(invoice), status=201)


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
    if not request.user.is_superuser and not SchoolAdminProfile.objects.filter(user=request.user).exists():
        return Response({"detail": "Only school admins can waive fees."}, status=403)
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
        },
        "payment": {
            "amount": _money(payment.amount), "method": payment.method,
            "method_display": payment.get_method_display(), "reference": payment.reference,
            "paid_at": payment.paid_at, "received_by": cashier, "notes": payment.notes,
        },
        "balances_verified": verified,
        "previous_balance": _money(previous) if verified else None,
        "balance_after": _money(after) if verified else None,
    })
