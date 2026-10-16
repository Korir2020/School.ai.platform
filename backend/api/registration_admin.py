from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.decorators import api_view, throttle_classes
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiResponse

from schools.models import MarkAuditLog, School, SchoolAdminProfile, SchoolRegistration
from .admin_throttle import RegistrationAdminThrottle


def _summary(reg):
    return {"id": reg.id, "reference": reg.reference, "school_name": reg.school_name, "school_code": reg.proposed_school_code, "school_type": reg.school_type, "school_email": reg.school_email, "school_phone": reg.school_phone, "county": reg.county, "administrator_name": reg.administrator_name, "administrator_username": reg.administrator_username, "administrator_email": reg.administrator_email, "status": reg.status, "verification_status": reg.verification_status, "created_at": reg.created_at, "updated_at": reg.updated_at, "reviewed_at": reg.reviewed_at, "rejection_reason": reg.rejection_reason if reg.status == "rejected" else "", "school_id": reg.school_id, "info_request_message": reg.info_request_message, "info_response_message": reg.info_response_message}


def _guard(request):
    if not request.user.is_authenticated or not request.user.is_superuser:
        return Response({"detail": "Only a system Superadmin can review school registrations."}, status=403)
    return None


@extend_schema(responses={200: OpenApiResponse(description="Superadmin-visible school registration summaries."), 403: OpenApiResponse(description="Superadmin authentication required.")})
@api_view(["GET"])
@throttle_classes([RegistrationAdminThrottle])
def registration_admin_list(request):
    denied = _guard(request)
    if denied: return denied
    status = request.GET.get("status")
    qs = SchoolRegistration.objects.all()
    if status in dict(SchoolRegistration.STATUSES): qs = qs.filter(status=status)
    return Response({"results": [_summary(x) for x in qs]})


@extend_schema(request=None, responses={200: OpenApiResponse(description="Registration approved or rejected."), 400: OpenApiResponse(description="Invalid action or missing rejection reason."), 403: OpenApiResponse(description="Superadmin authentication required."), 409: OpenApiResponse(description="Registration cannot transition to the requested state.")})
@api_view(["POST"])
@throttle_classes([RegistrationAdminThrottle])
def registration_admin_action(request, pk):
    denied = _guard(request)
    if denied: return denied
    action = str(request.data.get("action", "")).lower()
    with transaction.atomic():
        reg = SchoolRegistration.objects.select_for_update().filter(pk=pk).first()
        if not reg: return Response({"detail": "Registration not found."}, status=404)
        if action == "reject":
            if reg.status == "rejected": return Response(_summary(reg))
            if reg.status == "approved": return Response({"detail": "An approved registration cannot be rejected."}, status=409)
            reason = str(request.data.get("reason", "")).strip()
            if not reason: return Response({"detail": "A rejection reason is required."}, status=400)
            reg.status = "rejected"; reg.rejection_reason = reason; reg.reviewed_by = request.user; reg.reviewed_at = timezone.now(); reg.save(update_fields=["status", "rejection_reason", "reviewed_by", "reviewed_at", "updated_at"])
            MarkAuditLog.objects.create(school=None, user=request.user, action="school_reg_rejected", details={"reference": reg.reference, "reason": reason})
            return Response(_summary(reg))
        if action == "request_information":
            message = str(request.data.get("message", "")).strip()
            if not message: return Response({"detail": "A message explaining what is missing is required."}, status=400)
            if len(message) > 2000: return Response({"detail": "The message is too long (2000 characters at most)."}, status=400)
            if reg.status in ("approved", "rejected"): return Response({"detail": "A finished registration cannot be sent back for information."}, status=409)
            if reg.status == "needs_information": return Response({"detail": "Information has already been requested and is awaiting the applicant."}, status=409)
            if reg.verification_status != "verified": return Response({"detail": "The administrator email must be verified first."}, status=409)
            reg.status = "needs_information"; reg.info_request_message = message; reg.info_response_message = ""
            reg.save(update_fields=["status", "info_request_message", "info_response_message", "updated_at"])
            MarkAuditLog.objects.create(school=None, user=request.user, action="school_reg_info_asked", details={"reference": reg.reference, "message": message})
            return Response(_summary(reg))
        if action == "approve" and reg.status == "needs_information":
            return Response({"detail": "This registration is waiting for the applicant to reply to a request for information."}, status=409)
        if action != "approve": return Response({"detail": "Action must be approve or reject."}, status=400)
        if reg.verification_status != "verified":
            return Response({"detail": "The administrator email must be verified before approval."}, status=409)
        if reg.status == "approved" and reg.school_id:
            return Response(_summary(reg))
        if reg.status == "rejected": return Response({"detail": "A rejected registration must be resubmitted."}, status=409)
        if School.objects.filter(code__iexact=reg.proposed_school_code).exclude(pk=reg.school_id).exists(): return Response({"detail": "The school code is already in use."}, status=409)
        existing = User.objects.filter(username__iexact=reg.administrator_username).first()
        if existing and not reg.school_id: return Response({"detail": "The administrator username is already in use."}, status=409)
        if existing and not SchoolAdminProfile.objects.filter(user=existing, school_id=reg.school_id).exists(): return Response({"detail": "The administrator username is already in use."}, status=409)
        try:
            if reg.school_id:
                school = reg.school
            else:
                school = School.objects.create(name=reg.school_name, code=reg.proposed_school_code, school_type=reg.school_type, location=reg.address, email=reg.school_email, phone=reg.school_phone)
            if existing:
                user = existing
            else:
                user = User(username=reg.administrator_username, email=reg.administrator_email, first_name=reg.administrator_name[:150])
                user.password = reg.password_hash
                user.save()
            SchoolAdminProfile.objects.get_or_create(user=user, school=school, defaults={"is_deputy": False})
            reg.school = school; reg.status = "approved"; reg.reviewed_by = request.user; reg.reviewed_at = timezone.now(); reg.save(update_fields=["school", "status", "reviewed_by", "reviewed_at", "updated_at"])
            MarkAuditLog.objects.create(school=school, user=request.user, action="school_reg_approved", details={"reference": reg.reference, "school_id": school.id, "administrator_username": user.username})
        except IntegrityError:
            return Response({"detail": "The registration could not be approved because a unique record already exists."}, status=409)
        return Response(_summary(reg))
