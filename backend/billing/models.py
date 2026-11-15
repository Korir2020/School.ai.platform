import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone


class BillingConfiguration(models.Model):
    """Owner-configurable platform prices and commercial decisions.

    The singleton uses pk=1. Unapproved commercial decisions are explicitly
    represented as pending/null rather than presented as settled policy.
    """
    term_minimum_kes = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("5000.00"))
    per_student_term_kes = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("60.00"))
    terms_per_year = models.PositiveSmallIntegerField(default=3)
    annual_discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("10.00"))
    perpetual_annual_multiplier = models.PositiveSmallIntegerField(default=3)
    cloud_service_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("25.00"))
    school_hosted_maintenance_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    school_hosted_maintenance_approved = models.BooleanField(default=False)
    vat_treatment = models.CharField(max_length=20, default="undecided", choices=[("undecided", "Undecided"), ("inclusive", "Inclusive"), ("exclusive", "Exclusive")])
    post_expiry_policy = models.CharField(max_length=24, default="unrestricted", choices=[("unrestricted", "Unrestricted pending approval"), ("read_only_history", "Historical records read-only"), ("support_only", "Support and historical access")])
    post_expiry_policy_approved = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        verbose_name = "platform billing configuration"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)


class BillingProfile(models.Model):
    ACCESS_CHOICES = [("trial", "Free trial"), ("subscription", "Subscription"), ("perpetual", "Perpetual licence")]
    STATUS_CHOICES = [(v, v.replace("_", " ").title()) for v in (
        "unconfigured", "trial_active", "trial_completed", "payment_pending",
        "subscription_active", "subscription_expired", "licence_active",
        "service_expired", "suspended")]
    school = models.OneToOneField("schools.School", on_delete=models.CASCADE, related_name="billing_profile")
    access_type = models.CharField(max_length=16, choices=ACCESS_CHOICES, default="trial")
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default="unconfigured", db_index=True)
    licensed_capacity = models.PositiveIntegerField(null=True, blank=True)
    trial_started_at = models.DateTimeField(null=True, blank=True)
    trial_completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class BillingTrialCycle(models.Model):
    STATUSES = [("in_progress", "In progress"), ("completed", "Completed"), ("abandoned", "Abandoned")]
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="billing_trial_cycles")
    term = models.ForeignKey("schools.Term", on_delete=models.PROTECT, related_name="billing_trial_cycles")
    assessment_type = models.CharField(max_length=10)
    expected_class_level_ids = models.JSONField(default=list)
    status = models.CharField(max_length=16, choices=STATUSES, default="in_progress", db_index=True)
    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    completion_summary = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["school", "term", "assessment_type"], name="billing_trial_cycle_school_period_uniq")]
        indexes = [models.Index(fields=["school", "status"], name="bill_trial_school_status_idx")]


class BillingTrialEvidence(models.Model):
    KINDS = [(v, v.replace("_", " ").title()) for v in ("exam_created", "exam_published", "analytics_generated", "report_generated")]
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="billing_trial_evidence")
    cycle = models.ForeignKey(BillingTrialCycle, on_delete=models.CASCADE, related_name="evidence")
    exam = models.ForeignKey("schools.Exam", on_delete=models.CASCADE, related_name="billing_trial_evidence")
    kind = models.CharField(max_length=24, choices=KINDS)
    student = models.ForeignKey("schools.Student", null=True, blank=True, on_delete=models.CASCADE, related_name="billing_trial_evidence")
    evidence_key = models.CharField(max_length=120, unique=True)
    details = models.JSONField(default=dict, blank=True)
    occurred_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [models.Index(fields=["cycle", "kind"], name="bill_evidence_cycle_kind_idx")]


class BillingSubscription(models.Model):
    FREQUENCIES = [("termly", "Termly"), ("annual", "Annual")]
    STATUSES = [("active", "Active"), ("expired", "Expired"), ("cancelled", "Cancelled")]
    school = models.ForeignKey("schools.School", on_delete=models.PROTECT, related_name="platform_subscriptions")
    frequency = models.CharField(max_length=10, choices=FREQUENCIES)
    status = models.CharField(max_length=12, choices=STATUSES, default="active", db_index=True)
    capacity = models.PositiveIntegerField()
    starts_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField()
    invoice = models.ForeignKey("PlatformInvoice", null=True, blank=True, on_delete=models.PROTECT, related_name="subscriptions")
    created_at = models.DateTimeField(auto_now_add=True)


class PerpetualLicence(models.Model):
    DEPLOYMENT = [("cloud", "Marian cloud hosted"), ("school_hosted", "School hosted")]
    STATUSES = [("active", "Active"), ("revoked", "Revoked")]
    school = models.ForeignKey("schools.School", on_delete=models.PROTECT, related_name="perpetual_licences")
    licence_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    deployment_type = models.CharField(max_length=16, choices=DEPLOYMENT)
    status = models.CharField(max_length=12, choices=STATUSES, default="active")
    capacity = models.PositiveIntegerField()
    licensed_version = models.CharField(max_length=40, default="current")
    issued_at = models.DateTimeField(default=timezone.now)
    service_until = models.DateTimeField(null=True, blank=True)
    invoice = models.ForeignKey("PlatformInvoice", null=True, blank=True, on_delete=models.PROTECT, related_name="licences")
    created_at = models.DateTimeField(auto_now_add=True)


class PopulationSnapshot(models.Model):
    school = models.ForeignKey("schools.School", on_delete=models.PROTECT, related_name="billing_population_snapshots")
    academic_year = models.ForeignKey("schools.AcademicYear", null=True, blank=True, on_delete=models.SET_NULL)
    active_students = models.PositiveIntegerField()
    licensed_capacity = models.PositiveIntegerField(null=True, blank=True)
    reason = models.CharField(max_length=20, choices=[("invoice", "Invoice"), ("renewal", "Renewal"), ("capacity", "Capacity request")])
    created_at = models.DateTimeField(default=timezone.now)
    invoice = models.ForeignKey("PlatformInvoice", null=True, blank=True, on_delete=models.SET_NULL, related_name="population_snapshots")

    class Meta:
        indexes = [models.Index(fields=["school", "created_at"], name="bill_population_school_idx")]


class PlatformInvoice(models.Model):
    KINDS = [(v, v.replace("_", " ").title()) for v in ("termly_subscription", "annual_subscription", "perpetual_licence", "cloud_service", "school_maintenance")]
    STATUSES = [("outstanding", "Outstanding"), ("paid", "Paid"), ("void", "Void")]
    school = models.ForeignKey("schools.School", on_delete=models.PROTECT, related_name="platform_invoices")
    invoice_number = models.CharField(max_length=32, unique=True, default="")
    kind = models.CharField(max_length=24, choices=KINDS)
    amount_kes = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    currency = models.CharField(max_length=3, default="KES")
    active_student_snapshot = models.PositiveIntegerField()
    capacity_snapshot = models.PositiveIntegerField(null=True, blank=True)
    academic_year_snapshot = models.CharField(max_length=20, blank=True)
    calculation = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=16, choices=STATUSES, default="outstanding", db_index=True)
    due_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="created_platform_invoices")
    created_at = models.DateTimeField(default=timezone.now)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["school", "status"], name="bill_invoice_school_status_idx")]

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            self.invoice_number = f"MAR-{uuid.uuid4().hex[:12].upper()}"
        super().save(*args, **kwargs)


class PlatformPayment(models.Model):
    METHODS = [("bank_transfer", "Bank transfer"), ("mpesa_stk", "M-Pesa STK"), ("mpesa_paybill", "M-Pesa Paybill"), ("gateway", "Payment gateway")]
    STATUSES = [(v, v.title()) for v in ("pending", "successful", "failed", "reversed")]
    invoice = models.ForeignKey(PlatformInvoice, on_delete=models.PROTECT, related_name="payments")
    method = models.CharField(max_length=20, choices=METHODS)
    status = models.CharField(max_length=12, choices=STATUSES, default="pending", db_index=True)
    amount_kes = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    client_reference = models.CharField(max_length=100, blank=True)
    provider_transaction_id = models.CharField(max_length=120, null=True, blank=True)
    idempotency_key = models.CharField(max_length=80, unique=True)
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="submitted_platform_payments")
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="verified_platform_payments")
    created_at = models.DateTimeField(default=timezone.now)
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["method", "provider_transaction_id"], condition=Q(provider_transaction_id__isnull=False), name="platform_provider_transaction_unique")]


class PaymentCallbackEvent(models.Model):
    provider = models.CharField(max_length=32)
    event_id = models.CharField(max_length=120)
    payload_sha256 = models.CharField(max_length=64)
    payment = models.ForeignKey(PlatformPayment, null=True, blank=True, on_delete=models.SET_NULL, related_name="callback_events")
    received_at = models.DateTimeField(default=timezone.now)
    outcome = models.CharField(max_length=24, default="received")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["provider", "event_id"], name="platform_callback_event_unique")]


class CapacityUpgradeRequest(models.Model):
    STATUSES = [(v, v.title()) for v in ("pending", "approved", "rejected")]
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="capacity_upgrade_requests")
    current_capacity = models.PositiveIntegerField(null=True, blank=True)
    active_students_snapshot = models.PositiveIntegerField()
    requested_capacity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    status = models.CharField(max_length=12, choices=STATUSES, default="pending", db_index=True)
    reason = models.CharField(max_length=500, blank=True)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="requested_capacity_upgrades")
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="reviewed_capacity_upgrades")
    review_note = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    reviewed_at = models.DateTimeField(null=True, blank=True)


class BillingAuditLog(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="platform_billing_audit_events")
    school = models.ForeignKey("schools.School", null=True, blank=True, on_delete=models.SET_NULL, related_name="platform_billing_audit_events")
    action = models.CharField(max_length=40)
    object_type = models.CharField(max_length=40, blank=True)
    object_id = models.CharField(max_length=80, blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["school", "created_at"], name="bill_audit_school_date_idx")]
