import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Count, Sum
from django.http import JsonResponse
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied

from schools.models import AcademicYear, School, SchoolAdminProfile, Term
from api.permissions import IsSuperAdmin
from .models import (
    BillingAuditLog, BillingConfiguration, BillingProfile, BillingSubscription,
    BillingTrialCycle, CapacityUpgradeRequest, PerpetualLicence,
    PlatformInvoice, PlatformPayment, PaymentCallbackEvent,
)
from .services import (
    active_population, active_trial_cycle, can_start_exam_cycle, config, effective_status,
    cycle_progress, price_table, record_audit, school_profile,
    snapshot_population,
)


def _school_admin_school(user):
    if not user or not user.is_authenticated or user.is_superuser:
        raise PermissionDenied("School billing is available only to a school administrator.")
    profile = SchoolAdminProfile.objects.filter(user=user, is_deputy=False).select_related("school").first()
    if profile is None:
        raise PermissionDenied("School billing is available only to a full school administrator.")
    return profile.school


def _cycle_payload(school_id):
    cycle = active_trial_cycle(school_id)
    if cycle is None:
        cycle = BillingTrialCycle.objects.filter(school_id=school_id).order_by("-started_at", "-pk").first()
    return cycle_progress(cycle) if cycle else None


def _prices_for(school_id):
    count, year = active_population(school_id)
    table = price_table(count)
    return count, year, table


def _invoice_data(invoice):
    payments = list(invoice.payments.order_by("-created_at").values(
        "id", "method", "status", "amount_kes", "client_reference", "provider_transaction_id", "created_at", "verified_at"))
    return {
        "id": invoice.pk, "invoice_number": invoice.invoice_number,
        "kind": invoice.kind, "amount_kes": str(invoice.amount_kes), "currency": invoice.currency,
        "active_student_snapshot": invoice.active_student_snapshot,
        "capacity_snapshot": invoice.capacity_snapshot,
        "academic_year_snapshot": invoice.academic_year_snapshot,
        "calculation": invoice.calculation, "status": invoice.status,
        "due_at": invoice.due_at, "created_at": invoice.created_at,
        "paid_at": invoice.paid_at, "payments": payments,
    }


def _profile_status(profile):
    return effective_status(profile)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def school_billing(request):
    school = _school_admin_school(request.user)
    profile = school_profile(school.pk)
    count, year, prices = _prices_for(school.pk)
    invoices = [_invoice_data(row) for row in PlatformInvoice.objects.filter(school=school).prefetch_related("payments")[:50]]
    capacity = profile.licensed_capacity
    subscription = BillingSubscription.objects.filter(school=school, status="active").order_by("-ends_at").first()
    licence = PerpetualLicence.objects.filter(school=school, status="active").order_by("-issued_at").first()
    config_row = config()
    maintenance = prices["school_maintenance_annual_kes"]
    return Response({
        "school": {"id": school.pk, "name": school.name, "code": school.code},
        "access_type": profile.access_type, "status": _profile_status(profile),
        "trial_started_at": profile.trial_started_at, "trial_completed_at": profile.trial_completed_at,
        "trial_progress": _cycle_payload(school.pk),
        "active_students": count, "active_academic_year": year.name if year else None,
        "licensed_capacity": capacity, "over_capacity": capacity is not None and count > capacity,
        "pricing": {"termly_kes": str(prices["termly_kes"]), "annual_kes": str(prices["annual_kes"]),
                    "annual_discount_percent": str(config_row.annual_discount_percent),
                    "perpetual_kes": str(prices["perpetual_kes"]),
                    "cloud_service_annual_kes": str(prices["cloud_service_annual_kes"]),
                    "school_hosted_maintenance_annual_kes": str(maintenance) if maintenance is not None else None,
                    "school_hosted_maintenance_approved": config_row.school_hosted_maintenance_approved,
                    "currency": "KES", "vat_treatment": config_row.vat_treatment},
        "subscription": {"frequency": subscription.frequency, "status": subscription.status,
                         "capacity": subscription.capacity, "starts_at": subscription.starts_at,
                         "ends_at": subscription.ends_at} if subscription else None,
        "perpetual_licence": {"deployment_type": licence.deployment_type, "capacity": licence.capacity,
                               "licensed_version": licence.licensed_version, "issued_at": licence.issued_at,
                               "service_until": licence.service_until,
                               "ongoing_service_status": "active" if not licence.service_until or licence.service_until > timezone.now() else "expired"} if licence else None,
        "outstanding_kes": str(PlatformInvoice.objects.filter(school=school, status="outstanding").aggregate(v=Sum("amount_kes"))["v"] or Decimal("0.00")),
        "invoices": invoices,
        "capacity_requests": list(CapacityUpgradeRequest.objects.filter(school=school).order_by("-created_at").values("id", "current_capacity", "active_students_snapshot", "requested_capacity", "status", "reason", "review_note", "created_at", "reviewed_at")[:20]),
        "payments_live": False,
        "payment_message": "M-Pesa and other live gateways are not enabled. Bank-transfer submissions remain pending until a Marian Super Administrator verifies settlement.",
        "support_action": "Help",
        "commercial_decisions_pending": {"vat_treatment": config_row.vat_treatment == "undecided",
                                         "post_expiry_policy": not config_row.post_expiry_policy_approved,
                                         "school_hosted_maintenance": not config_row.school_hosted_maintenance_approved},
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def school_invoice_request(request):
    school = _school_admin_school(request.user)
    kind = str(request.data.get("kind", ""))
    if kind not in {"termly_subscription", "annual_subscription", "perpetual_licence"}:
        return Response({"detail": "School admins can request a termly subscription, annual subscription or Marian cloud perpetual licence."}, status=400)
    if kind == "perpetual_licence" and PerpetualLicence.objects.filter(school=school, status="active", deployment_type="cloud").exists():
        return Response({"detail": "An active cloud perpetual licence already exists for this school."}, status=409)
    pending = PlatformInvoice.objects.filter(school=school, kind=kind, status="outstanding").first()
    if pending:
        return Response({"detail": "An outstanding invoice of this type already exists.", "invoice": _invoice_data(pending)}, status=409)
    count, year = active_population(school.pk)
    profile = school_profile(school.pk)
    capacity = max(count, profile.licensed_capacity or 0, 1)
    prices = price_table(capacity)
    amount = prices["termly_kes"] if kind == "termly_subscription" else prices["annual_kes"] if kind == "annual_subscription" else prices["perpetual_kes"]
    invoice = PlatformInvoice.objects.create(
        school=school, kind=kind, amount_kes=amount,
        active_student_snapshot=count, capacity_snapshot=capacity,
        academic_year_snapshot=year.name if year else "",
        calculation={"active_students": count, "billable_capacity": capacity,
                     "termly_kes": str(prices["termly_kes"]),
                     "annual_kes": str(prices["annual_kes"]),
                     "annual_discount_percent": str(config().annual_discount_percent),
                     "perpetual_annual_multiplier": config().perpetual_annual_multiplier,
                     "payment_live": False},
    )
    snapshot_population(school.pk, "invoice", invoice)
    record_audit(actor=request.user, action="school_invoice_requested", school=school,
                 obj=invoice, details={"kind": kind, "amount_kes": str(amount),
                                       "active_students": count, "capacity": capacity})
    return Response(_invoice_data(invoice), status=201)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def school_capacity_request(request):
    school = _school_admin_school(request.user)
    profile = school_profile(school.pk)
    count, _year = active_population(school.pk)
    try:
        capacity = int(request.data.get("requested_capacity"))
    except (TypeError, ValueError):
        return Response({"detail": "Enter a valid student capacity."}, status=400)
    if capacity <= max(count, profile.licensed_capacity or 0):
        return Response({"detail": "Requested capacity must exceed both the current licensed capacity and current active student count."}, status=400)
    if CapacityUpgradeRequest.objects.filter(school=school, status="pending").exists():
        return Response({"detail": "A capacity request is already awaiting review."}, status=409)
    row = CapacityUpgradeRequest.objects.create(
        school=school, current_capacity=profile.licensed_capacity,
        active_students_snapshot=count, requested_capacity=capacity,
        reason=str(request.data.get("reason", ""))[:500], requested_by=request.user,
    )
    record_audit(actor=request.user, action="capacity_upgrade_requested", school=school, obj=row,
                 details={"requested_capacity": capacity, "active_students": count})
    return Response({"id": row.pk, "status": row.status, "requested_capacity": capacity,
                     "active_students_snapshot": count, "detail": "Request sent for review. No charge has been made."}, status=201)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def school_submit_bank_transfer(request):
    school = _school_admin_school(request.user)
    invoice_id = request.data.get("invoice_id")
    reference = str(request.data.get("reference", "")).strip()[:100]
    key = str(request.headers.get("Idempotency-Key") or request.data.get("idempotency_key", "")).strip()[:80]
    if not key:
        return Response({"detail": "An Idempotency-Key is required."}, status=400)
    if not reference:
        return Response({"detail": "Enter the bank transfer reference. This reference is not proof of settlement."}, status=400)
    invoice = PlatformInvoice.objects.filter(pk=invoice_id, school=school, status="outstanding").first()
    if invoice is None:
        return Response({"detail": "Outstanding invoice not found."}, status=404)
    try:
        with transaction.atomic():
            existing = PlatformPayment.objects.filter(idempotency_key=key).first()
            if existing:
                if existing.invoice_id != invoice.pk or existing.method != "bank_transfer":
                    return Response({"detail": "Idempotency key was already used for a different payment."}, status=409)
                payment = existing
            else:
                payment = PlatformPayment.objects.create(
                    invoice=invoice, method="bank_transfer", amount_kes=invoice.amount_kes,
                    client_reference=reference, idempotency_key=key,
                    submitted_by=request.user, status="pending",
                )
    except IntegrityError:
        payment = PlatformPayment.objects.filter(idempotency_key=key, invoice=invoice).first()
        if payment is None:
            return Response({"detail": "Duplicate payment request."}, status=409)
    record_audit(actor=request.user, action="bank_transfer_submitted", school=school, obj=payment,
                 details={"invoice": invoice.invoice_number, "reference": reference, "status": "pending"})
    return Response({"payment_id": payment.pk, "status": payment.status,
                     "detail": "Payment submission is pending manual settlement verification. No access has been activated."}, status=202)


def _admin_invoice_list(query=None):
    qs = PlatformInvoice.objects.select_related("school").prefetch_related("payments")
    if query:
        qs = qs.filter(school__name__icontains=query) | qs.filter(invoice_number__icontains=query)
    return [_invoice_data(x) | {"school_name": x.school.name, "school_id": x.school_id} for x in qs[:200]]


def _school_billing_record(school):
    profile = school_profile(school.pk)
    count, year = active_population(school.pk)
    cycle = _cycle_payload(school.pk)
    active_sub = BillingSubscription.objects.filter(school=school, status="active").order_by("-ends_at").first()
    licence = PerpetualLicence.objects.filter(school=school, status="active").order_by("-issued_at").first()
    prices = price_table(max(count, profile.licensed_capacity or 0))
    return {"school_id": school.pk, "school_name": school.name, "code": school.code,
            "access_type": profile.access_type, "status": _profile_status(profile),
            "active_students": count, "active_academic_year": year.name if year else None,
            "licensed_capacity": profile.licensed_capacity,
            "over_capacity": profile.licensed_capacity is not None and count > profile.licensed_capacity,
            "termly_kes": str(prices["termly_kes"]), "annual_kes": str(prices["annual_kes"]),
            "trial_progress": cycle,
            "trial_started_at": profile.trial_started_at,
            "subscription_ends_at": active_sub.ends_at if active_sub else None,
            "licence_deployment": licence.deployment_type if licence else None,
            "licence_service_until": licence.service_until if licence else None,
            "outstanding_invoices": PlatformInvoice.objects.filter(school=school, status="outstanding").count()}


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsSuperAdmin])
def admin_billing_overview(request):
    schools = School.objects.all().order_by("name")
    q = str(request.query_params.get("q", "")).strip()
    status_filter = str(request.query_params.get("status", "")).strip()
    if q:
        schools = schools.filter(name__icontains=q) | schools.filter(code__icontains=q)
    records = [_school_billing_record(s) for s in schools[:300]]
    if status_filter:
        records = [r for r in records if r["status"] == status_filter]
    invoices = PlatformInvoice.objects.all()
    payments = PlatformPayment.objects.all()
    payload = {
        "summary": {
            "registered_schools": School.objects.count(),
            "trials_active": BillingProfile.objects.filter(status="trial_active").count(),
            "trials_awaiting_completion": BillingTrialCycle.objects.filter(status="in_progress").count(),
            "trials_completed": BillingProfile.objects.filter(status="trial_completed").count(),
            "active_subscriptions": BillingSubscription.objects.filter(status="active", ends_at__gt=timezone.now()).count(),
            "expired_subscriptions": BillingSubscription.objects.filter(status="expired").count(),
            "perpetual_licences": PerpetualLicence.objects.filter(status="active").count(),
            "cloud_licences": PerpetualLicence.objects.filter(status="active", deployment_type="cloud").count(),
            "school_hosted_licences": PerpetualLicence.objects.filter(status="active", deployment_type="school_hosted").count(),
            "pending_payments": payments.filter(status="pending").count(),
            "successful_payments": payments.filter(status="successful").count(),
            "failed_payments": payments.filter(status="failed").count(),
            "outstanding_invoices": invoices.filter(status="outstanding").count(),
            "upcoming_renewals": BillingSubscription.objects.filter(status="active", ends_at__gte=timezone.now(), ends_at__lte=timezone.now()+timedelta(days=30)).count(),
            "over_capacity_schools": sum(1 for r in records if r["over_capacity"]),
            "successful_kes": str(payments.filter(status="successful").aggregate(v=Sum("amount_kes"))["v"] or Decimal("0.00")),
            "outstanding_kes": str(invoices.filter(status="outstanding").aggregate(v=Sum("amount_kes"))["v"] or Decimal("0.00")),
        },
        "schools": records, "invoices": _admin_invoice_list(q),
        "pending_payments": list(PlatformPayment.objects.filter(status="pending").select_related("invoice__school").values("id", "invoice__invoice_number", "invoice__school__name", "method", "amount_kes", "client_reference", "created_at")[:100]),
        "capacity_requests": list(CapacityUpgradeRequest.objects.filter(status="pending").select_related("school").values("id", "school_id", "school__name", "current_capacity", "active_students_snapshot", "requested_capacity", "reason", "created_at")[:100]),
        "payment_readiness": {"live_enabled": False, "providers": ["mpesa_stk", "mpesa_paybill", "bank_transfer", "gateway"],
                              "detail": "No live gateway is configured. Provider approval, credentials, callback URL registration and production reconciliation remain required."},
    }
    return Response(payload)


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsSuperAdmin])
def admin_billing_school_detail(request, school_id):
    school = School.objects.filter(pk=school_id).first()
    if not school:
        return Response({"detail": "Not found."}, status=404)
    return Response({"school": _school_billing_record(school),
                     "invoices": [_invoice_data(x) for x in PlatformInvoice.objects.filter(school=school).prefetch_related("payments")[:100]],
                     "payments": list(PlatformPayment.objects.filter(invoice__school=school).select_related("invoice").values("id", "invoice__invoice_number", "method", "status", "amount_kes", "client_reference", "provider_transaction_id", "created_at", "verified_at")[:100]),
                     "capacity_requests": list(CapacityUpgradeRequest.objects.filter(school=school).values("id", "requested_capacity", "status", "reason", "review_note", "created_at", "reviewed_at")),
                     "audit": list(BillingAuditLog.objects.filter(school=school).values("id", "actor__username", "action", "object_type", "object_id", "details", "created_at")[:100])})


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated, IsSuperAdmin])
def admin_billing_pricing(request):
    row = config()
    fields = ["term_minimum_kes", "per_student_term_kes", "terms_per_year",
              "annual_discount_percent", "perpetual_annual_multiplier",
              "cloud_service_percent", "school_hosted_maintenance_percent",
              "school_hosted_maintenance_approved", "vat_treatment",
              "post_expiry_policy", "post_expiry_policy_approved"]
    if request.method == "PATCH":
        old = {k: str(getattr(row, k)) for k in fields}
        data = request.data
        try:
            for k in fields:
                if k in data:
                    v = data[k]
                    if k in {"term_minimum_kes", "per_student_term_kes", "annual_discount_percent", "cloud_service_percent", "school_hosted_maintenance_percent"}:
                        setattr(row, k, None if v in (None, "") and k == "school_hosted_maintenance_percent" else Decimal(str(v)))
                    elif k in {"terms_per_year", "perpetual_annual_multiplier"}:
                        setattr(row, k, int(v))
                    elif k in {"school_hosted_maintenance_approved", "post_expiry_policy_approved"}:
                        if not isinstance(v, bool):
                            raise ValueError("Approval flags must be true or false.")
                        setattr(row, k, v)
                    elif k == "vat_treatment":
                        if v not in {"undecided", "inclusive", "exclusive"}:
                            raise ValueError("Invalid VAT treatment.")
                        row.vat_treatment = v
                    elif k == "post_expiry_policy":
                        if v not in {"unrestricted", "read_only_history", "support_only"}:
                            raise ValueError("Invalid post-expiry policy.")
                        row.post_expiry_policy = v
            if row.term_minimum_kes < 0 or row.per_student_term_kes < 0 or not 1 <= row.terms_per_year <= 4:
                raise ValueError("Pricing values must be non-negative and terms per year between 1 and 4.")
            if not 1 <= row.perpetual_annual_multiplier <= 20:
                raise ValueError("Perpetual multiplier must be between 1 and 20.")
            if not 0 <= row.annual_discount_percent <= 100 or not 0 <= row.cloud_service_percent <= 100:
                raise ValueError("Percentages must be between 0 and 100.")
            if row.school_hosted_maintenance_percent is not None and not 0 <= row.school_hosted_maintenance_percent <= 100:
                raise ValueError("Maintenance rate must be between 0 and 100.")
        except (ValueError, InvalidOperation, TypeError) as exc:
            return Response({"detail": str(exc)}, status=400)
        row.updated_by = request.user
        row.save()
        record_audit(actor=request.user, action="pricing_configuration_changed", details={
            "before": old, "after": {k: str(getattr(row, k)) for k in fields}})
    return Response({k: (str(getattr(row, k)) if isinstance(getattr(row, k), Decimal) or getattr(row, k) is None else getattr(row, k)) for k in fields} | {"updated_at": row.updated_at, "updated_by": row.updated_by_id})


def _add_months(value, months):
    month = value.month - 1 + months
    year = value.year + month // 12
    month = month % 12 + 1
    import calendar
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsSuperAdmin])
def admin_create_invoice(request):
    school = School.objects.filter(pk=request.data.get("school_id")).first()
    if not school:
        return Response({"detail": "School not found."}, status=404)
    kind = str(request.data.get("kind", ""))
    allowed = {"termly_subscription", "annual_subscription", "perpetual_licence", "cloud_service", "school_maintenance"}
    if kind not in allowed:
        return Response({"detail": "Unsupported invoice type."}, status=400)
    count, year = active_population(school.pk)
    profile = school_profile(school.pk)
    cfg = config()
    try:
        requested_capacity = int(request.data.get("capacity") or profile.licensed_capacity or count or 1)
    except (TypeError, ValueError):
        return Response({"detail": "Capacity must be a whole number."}, status=400)
    if requested_capacity < count or requested_capacity < 1:
        return Response({"detail": "Licensed capacity cannot be below the verified active student population."}, status=400)
    prices = price_table(requested_capacity, cfg)
    deployment = str(request.data.get("deployment_type", "cloud"))
    if kind == "termly_subscription":
        amount, frequency = prices["termly_kes"], "termly"
    elif kind == "annual_subscription":
        amount, frequency = prices["annual_kes"], "annual"
    elif kind == "perpetual_licence":
        if deployment == "school_hosted":
            return Response({"detail": "School-hosted perpetual deployment is not being sold as production-ready: the source project lacks a supported installer, independent upgrade process and school-only recovery path. Contact support for the documented phased plan."}, status=409)
        if deployment != "cloud":
            return Response({"detail": "Choose the Marian cloud deployment option."}, status=400)
        amount, frequency = prices["perpetual_kes"], None
    elif kind == "cloud_service":
        if not PerpetualLicence.objects.filter(school=school, status="active", deployment_type="cloud").exists():
            return Response({"detail": "Cloud service renewal requires an active cloud perpetual licence."}, status=409)
        amount, frequency = prices["cloud_service_annual_kes"], None
    else:
        if not cfg.school_hosted_maintenance_approved or cfg.school_hosted_maintenance_percent is None:
            return Response({"detail": "School-hosted maintenance pricing is not approved. No maintenance invoice can be issued."}, status=409)
        if not PerpetualLicence.objects.filter(school=school, status="active", deployment_type="school_hosted").exists():
            return Response({"detail": "No active school-hosted licence is recorded."}, status=409)
        amount = prices["school_maintenance_annual_kes"]
        frequency = None
    if amount is None or amount <= 0:
        return Response({"detail": "Calculated invoice amount must be positive."}, status=400)
    calc = {"active_students": count, "billable_capacity": requested_capacity,
            "term_minimum_kes": str(cfg.term_minimum_kes), "per_student_term_kes": str(cfg.per_student_term_kes),
            "annual_discount_percent": str(cfg.annual_discount_percent),
            "terms_per_year": cfg.terms_per_year,
            "perpetual_annual_multiplier": cfg.perpetual_annual_multiplier,
            "cloud_service_percent": str(cfg.cloud_service_percent),
            "school_hosted_maintenance_percent": str(cfg.school_hosted_maintenance_percent) if cfg.school_hosted_maintenance_percent is not None else None,
            "maintenance_approved": cfg.school_hosted_maintenance_approved,
            "frequency": frequency, "deployment_type": deployment if kind in {"perpetual_licence", "school_maintenance"} else None,
            "school_hosted_deployment_production_ready": False}
    invoice = PlatformInvoice.objects.create(
        school=school, kind=kind, amount_kes=amount, active_student_snapshot=count,
        capacity_snapshot=requested_capacity, academic_year_snapshot=year.name if year else "",
        calculation=calc, created_by=request.user,
    )
    snapshot_population(school.pk, "invoice", invoice)
    record_audit(actor=request.user, action="platform_invoice_created", school=school, obj=invoice,
                 details={"kind": kind, "amount_kes": str(amount), "student_snapshot": count,
                          "capacity_snapshot": requested_capacity, "calculation": calc})
    return Response(_invoice_data(invoice), status=201)


def _invoice_entitlement(invoice, payment):
    school_id = invoice.school_id
    profile = school_profile(school_id)
    now = timezone.now()
    if invoice.kind in {"termly_subscription", "annual_subscription"}:
        months = 3 if invoice.kind == "termly_subscription" else 12
        active = BillingSubscription.objects.filter(school_id=school_id, status="active", ends_at__gt=now).order_by("-ends_at").first()
        starts_at = active.ends_at if active else now
        ends_at = _add_months(starts_at, months)
        BillingSubscription.objects.create(
            school_id=school_id, frequency="termly" if months == 3 else "annual",
            capacity=invoice.capacity_snapshot, starts_at=starts_at, ends_at=ends_at, invoice=invoice,
        )
        profile.access_type = "subscription"
        profile.status = "subscription_active"
        profile.licensed_capacity = invoice.capacity_snapshot
        profile.save(update_fields=["access_type", "status", "licensed_capacity", "updated_at"])
    elif invoice.kind == "perpetual_licence":
        licence = PerpetualLicence.objects.create(
            school_id=school_id, deployment_type="cloud", capacity=invoice.capacity_snapshot,
            service_until=_add_months(now, 12), invoice=invoice,
        )
        profile.access_type = "perpetual"
        profile.status = "licence_active"
        profile.licensed_capacity = invoice.capacity_snapshot
        profile.save(update_fields=["access_type", "status", "licensed_capacity", "updated_at"])
        return licence
    elif invoice.kind == "cloud_service":
        licence = PerpetualLicence.objects.filter(school_id=school_id, status="active", deployment_type="cloud").order_by("-issued_at").first()
        if licence:
            base = max(now, licence.service_until or now)
            licence.service_until = _add_months(base, 12)
            licence.save(update_fields=["service_until"])
            if profile.status in {"service_expired", "payment_pending"}:
                profile.access_type, profile.status = "perpetual", "licence_active"
                profile.save(update_fields=["access_type", "status", "updated_at"])
    elif invoice.kind == "school_maintenance":
        licence = PerpetualLicence.objects.filter(school_id=school_id, status="active", deployment_type="school_hosted").order_by("-issued_at").first()
        if licence:
            base = max(now, licence.service_until or now)
            licence.service_until = _add_months(base, 12)
            licence.save(update_fields=["service_until"])
    return None


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsSuperAdmin])
def admin_review_payment(request, payment_id):
    action = request.data.get("action")
    if action not in {"verify", "fail", "reverse"}:
        return Response({"detail": "Action must be verify, fail or reverse."}, status=400)
    with transaction.atomic():
        payment = PlatformPayment.objects.select_for_update().select_related("invoice__school").filter(pk=payment_id).first()
        if payment is None:
            return Response({"detail": "Not found."}, status=404)
        invoice = PlatformInvoice.objects.select_for_update().get(pk=payment.invoice_id)
        if action == "verify":
            if payment.status == "successful":
                return Response({"id": payment.pk, "status": payment.status, "detail": "Already verified."})
            if payment.status != "pending" or invoice.status != "outstanding":
                return Response({"detail": "Only pending payments for outstanding invoices can be verified."}, status=409)
            if payment.amount_kes != invoice.amount_kes:
                return Response({"detail": "Payment amount does not exactly match invoice."}, status=409)
            provider_ref = str(request.data.get("provider_transaction_id", "")).strip()[:120]
            payment.provider_transaction_id = provider_ref or None
            payment.status = "successful"
            payment.verified_by = request.user
            payment.verified_at = timezone.now()
            try:
                with transaction.atomic():
                    payment.save(update_fields=["provider_transaction_id", "status", "verified_by", "verified_at"])
            except IntegrityError:
                return Response({"detail": "That provider transaction reference has already been used."}, status=409)
            invoice.status = "paid"
            invoice.paid_at = timezone.now()
            invoice.save(update_fields=["status", "paid_at"])
            _invoice_entitlement(invoice, payment)
            action_name = "platform_payment_verified"
        elif action == "fail":
            if payment.status != "pending":
                return Response({"detail": "Only a pending payment can be marked failed."}, status=409)
            payment.status = "failed"
            payment.verified_by = request.user
            payment.verified_at = timezone.now()
            payment.save(update_fields=["status", "verified_by", "verified_at"])
            action_name = "platform_payment_failed"
        else:
            if payment.status != "successful":
                return Response({"detail": "Only a successful payment can be reversed."}, status=409)
            payment.status = "reversed"
            payment.verified_by = request.user
            payment.verified_at = timezone.now()
            payment.save(update_fields=["status", "verified_by", "verified_at"])
            invoice.status = "outstanding"
            invoice.paid_at = None
            invoice.save(update_fields=["status", "paid_at"])
            profile = school_profile(invoice.school_id)
            if invoice.kind in {"annual_subscription", "termly_subscription"}:
                BillingSubscription.objects.filter(invoice=invoice, status="active").update(status="cancelled")
                profile.access_type, profile.status = "subscription", "payment_pending"
            elif invoice.kind == "perpetual_licence":
                PerpetualLicence.objects.filter(invoice=invoice, status="active").update(status="revoked")
                profile.access_type, profile.status = "trial", "payment_pending"
            elif invoice.kind == "cloud_service":
                profile.access_type, profile.status = "perpetual", "payment_pending"
            profile.save(update_fields=["access_type", "status", "updated_at"])
            action_name = "platform_payment_reversed"
        record_audit(actor=request.user, action=action_name, school=invoice.school, obj=payment,
                     details={"invoice": invoice.invoice_number, "amount_kes": str(payment.amount_kes),
                              "method": payment.method, "client_reference": payment.client_reference,
                              "provider_transaction_id": payment.provider_transaction_id,
                              "admin_note": str(request.data.get("note", ""))[:500]})
    return Response({"id": payment.pk, "status": payment.status, "invoice_status": invoice.status})


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsSuperAdmin])
def admin_capacity_decision(request, request_id):
    action = request.data.get("action")
    if action not in {"approve", "reject"}:
        return Response({"detail": "Action must be approve or reject."}, status=400)
    with transaction.atomic():
        row = CapacityUpgradeRequest.objects.select_for_update().select_related("school").filter(pk=request_id, status="pending").first()
        if row is None:
            return Response({"detail": "Pending request not found."}, status=404)
        count, _year = active_population(row.school_id)
        if action == "approve" and row.requested_capacity < count:
            return Response({"detail": "Verified active student count now exceeds the requested capacity. The school must request an updated capacity."}, status=409)
        row.status = "approved" if action == "approve" else "rejected"
        row.review_note = str(request.data.get("note", ""))[:500]
        row.reviewed_by = request.user
        row.reviewed_at = timezone.now()
        row.save(update_fields=["status", "review_note", "reviewed_by", "reviewed_at"])
        record_audit(actor=request.user, action=f"capacity_upgrade_{row.status}", school=row.school, obj=row,
                     details={"requested_capacity": row.requested_capacity, "note": row.review_note,
                              "active_students_at_review": count,
                              "detail": "Approval does not charge or change the licensed capacity; a priced invoice and verified payment are required." if action == "approve" else ""})
    return Response({"id": row.pk, "status": row.status,
                     "detail": "Capacity approved for purchase; no charge or capacity change has occurred." if action == "approve" else "Request rejected."})


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsSuperAdmin])
def admin_profile_update(request, school_id):
    school = School.objects.filter(pk=school_id).first()
    if not school:
        return Response({"detail": "Not found."}, status=404)
    profile = school_profile(school.pk)
    allowed_status = {v for v, _ in BillingProfile.STATUS_CHOICES}
    new_status = request.data.get("status")
    new_access = request.data.get("access_type")
    before = {"status": profile.status, "access_type": profile.access_type, "licensed_capacity": profile.licensed_capacity}
    if new_status is not None:
        if new_status not in allowed_status:
            return Response({"detail": "Invalid status."}, status=400)
        profile.status = new_status
    if new_access is not None:
        if new_access not in {"trial", "subscription", "perpetual"}:
            return Response({"detail": "Invalid access type."}, status=400)
        profile.access_type = new_access
    if "licensed_capacity" in request.data:
        try:
            capacity = int(request.data["licensed_capacity"]) if request.data["licensed_capacity"] is not None else None
        except (ValueError, TypeError):
            return Response({"detail": "Capacity must be a whole number or null."}, status=400)
        count, _year = active_population(school.pk)
        if capacity is not None and capacity < count:
            return Response({"detail": "Capacity cannot be set below the verified active student count."}, status=400)
        profile.licensed_capacity = capacity
    if profile.status == "subscription_active":
        if profile.access_type != "subscription" or not BillingSubscription.objects.filter(
            school=school, status="active", ends_at__gt=timezone.now(),
        ).exists():
            return Response({"detail": "A subscription can be activated only by a verified paid invoice with a current subscription record. Manual status changes cannot grant paid access."}, status=409)
    if profile.status == "licence_active":
        if profile.access_type != "perpetual" or not PerpetualLicence.objects.filter(school=school, status="active").exists():
            return Response({"detail": "A perpetual licence can be activated only by a verified paid invoice with an active licence record."}, status=409)
    if profile.status == "trial_active":
        if profile.access_type != "trial" or profile.trial_completed_at is not None or BillingTrialCycle.objects.filter(school=school, status="completed").exists():
            return Response({"detail": "A completed or paid account cannot be manually reset to a free trial."}, status=409)
    if profile.status == "trial_active" and profile.trial_started_at is None:
        profile.trial_started_at = timezone.now()
    profile.save()
    after = {"status": profile.status, "access_type": profile.access_type, "licensed_capacity": profile.licensed_capacity}
    record_audit(actor=request.user, action="billing_profile_manually_changed", school=school,
                 details={"before": before, "after": after, "note": str(request.data.get("note", ""))[:500]})
    return Response(after)


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsSuperAdmin])
def admin_billing_audit(request):
    qs = BillingAuditLog.objects.select_related("school", "actor")
    if request.query_params.get("school_id", "").isdigit():
        qs = qs.filter(school_id=int(request.query_params["school_id"]))
    return Response(list(qs.values("id", "school_id", "school__name", "actor_id", "actor__username", "action", "object_type", "object_id", "details", "created_at")[:300]))


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def payment_callback(request):
    """Generic normalized webhook contract; remains disabled until a secret exists.

    Signature: lower-case/upper-case-insensitive hex HMAC-SHA256 of the exact
    request body, sent as X-Mar-Billing-Signature. No credentials are embedded.
    """
    secret = getattr(settings, "BILLING_WEBHOOK_SECRET", "") or os.environ.get("BILLING_WEBHOOK_SECRET", "")
    if len(secret) < 32:
        return Response({"detail": "Payment callbacks are not enabled; provider credentials and approval are not configured."}, status=503)
    signature = request.headers.get("X-Mar-Billing-Signature", "").strip().lower()
    expected = hmac.new(secret.encode(), request.body, hashlib.sha256).hexdigest()
    if not signature or not hmac.compare_digest(signature, expected):
        return Response({"detail": "Invalid callback signature."}, status=401)
    try:
        data = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return Response({"detail": "Invalid JSON callback."}, status=400)
    provider = str(data.get("provider", "")).strip()[:32]
    event_id = str(data.get("event_id", "")).strip()[:120]
    ref = str(data.get("invoice_number", "")).strip()
    txn = str(data.get("transaction_id", "")).strip()[:120]
    status = str(data.get("status", "")).lower()
    if not provider or not event_id or not ref or not txn or status not in {"successful", "failed", "reversed"}:
        return Response({"detail": "Required normalized event fields are missing or invalid."}, status=400)
    digest = hashlib.sha256(request.body).hexdigest()
    with transaction.atomic():
        try:
            with transaction.atomic():
                event = PaymentCallbackEvent.objects.create(provider=provider, event_id=event_id, payload_sha256=digest, outcome="received")
        except IntegrityError:
            existing = PaymentCallbackEvent.objects.filter(provider=provider, event_id=event_id).first()
            if existing and existing.payload_sha256 != digest:
                return Response({"detail": "Event ID was replayed with a different payload."}, status=409)
            return Response({"duplicate": True, "outcome": existing.outcome if existing else "received"})
        invoice = PlatformInvoice.objects.select_for_update().filter(invoice_number=ref, currency="KES").first()
        if invoice is None:
            event.outcome = "unknown_invoice"
            event.save(update_fields=["outcome"])
            return Response({"detail": "Unknown invoice reference."}, status=404)
        try:
            amount = Decimal(str(data.get("amount_kes")))
        except (InvalidOperation, TypeError):
            event.outcome = "invalid_amount"
            event.save(update_fields=["outcome"])
            return Response({"detail": "Invalid amount."}, status=400)
        if amount != invoice.amount_kes or str(data.get("currency", "KES")).upper() != "KES":
            event.outcome = "amount_mismatch"
            event.save(update_fields=["outcome"])
            record_audit(actor=None, action="payment_callback_rejected", school=invoice.school, obj=event,
                         details={"reason": "amount_or_currency_mismatch", "invoice": ref, "amount": str(amount)})
            return Response({"detail": "Callback amount or currency does not match the invoice."}, status=409)
        if status == "successful" and invoice.status != "outstanding":
            event.outcome = "invoice_already_settled"
            event.save(update_fields=["outcome"])
            return Response({"detail": "Invoice is not outstanding."}, status=409)
        method = str(data.get("method", "gateway"))
        if method not in {"mpesa_stk", "mpesa_paybill", "gateway"}:
            event.outcome = "unsupported_method"
            event.save(update_fields=["outcome"])
            return Response({"detail": "Provider callback cannot settle this payment method."}, status=400)
        key = f"webhook:{provider}:{event_id}"[:80]
        if status == "reversed":
            payment = PlatformPayment.objects.select_for_update().filter(
                invoice=invoice, method=method, provider_transaction_id=txn,
                status="successful",
            ).first()
            if payment is None:
                event.outcome = "reversal_without_successful_payment"
                event.save(update_fields=["outcome"])
                return Response({"detail": "No successful payment matches the reversal transaction."}, status=409)
        else:
            try:
                with transaction.atomic():
                    payment, _ = PlatformPayment.objects.get_or_create(
                        idempotency_key=key,
                        defaults={"invoice": invoice, "method": method, "amount_kes": amount,
                                  "provider_transaction_id": txn, "status": "pending"},
                    )
            except IntegrityError:
                event.outcome = "duplicate_provider_transaction"
                event.save(update_fields=["outcome"])
                return Response({"detail": "Provider transaction has already been processed."}, status=409)
        event.payment = payment
        event.outcome = "accepted"
        event.save(update_fields=["payment", "outcome"])
        if status == "successful":
            payment.status = "successful"
            payment.verified_at = timezone.now()
            payment.save(update_fields=["status", "verified_at"])
            invoice.status = "paid"
            invoice.paid_at = timezone.now()
            invoice.save(update_fields=["status", "paid_at"])
            _invoice_entitlement(invoice, payment)
        elif status == "failed":
            payment.status = "failed"
            payment.save(update_fields=["status"])
        else:
            payment.status = "reversed"
            payment.save(update_fields=["status"])
            invoice.status, invoice.paid_at = "outstanding", None
            invoice.save(update_fields=["status", "paid_at"])
            BillingSubscription.objects.filter(invoice=invoice, status="active").update(status="cancelled")
            PerpetualLicence.objects.filter(invoice=invoice, status="active").update(status="revoked")
            BillingProfile.objects.filter(school=invoice.school).update(status="payment_pending")
        record_audit(actor=None, action=f"payment_callback_{status}", school=invoice.school, obj=payment,
                     details={"provider": provider, "event_id": event_id, "invoice": ref, "transaction_id": txn, "amount_kes": str(amount)})
    return Response({"accepted": True, "payment_id": payment.pk, "status": payment.status})
