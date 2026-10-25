from pathlib import Path

from django.conf import settings
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response

from schools.models import SchoolAdminProfile
from .views import _scope

_ALLOWED = {".png", ".jpg", ".jpeg", ".webp"}
_MAX_BYTES = 2 * 1024 * 1024


@api_view(["GET", "POST"])
@parser_classes([MultiPartParser, FormParser])
def school_branding(request):
    school_id, error = _scope(request)
    if error:
        return error
    if not request.user.is_superuser and not SchoolAdminProfile.objects.filter(user=request.user).exists():
        return Response({"detail": "Only school administrators can manage branding."}, status=403)
    school = request.user.school_admin_profile.school if not request.user.is_superuser else None
    if school is None and school_id is not None:
        from schools.models import School
        school = School.objects.filter(id=school_id).first()
    if school is None:
        return Response({"detail": "School not found."}, status=404)
    if request.method == "GET":
        return Response({"name": school.name, "code": school.code, "location": school.location,
                         "email": school.email, "phone": school.phone, "motto": school.motto, "principal_name": school.principal_name,
                         "logo_url": request.build_absolute_uri(school.logo.url) if school.logo else None})
    fields = []
    for key, limit in (("motto", 200), ("principal_name", 100)):
        if key in request.data:
            val = " ".join(str(request.data.get(key) or "").split())
            if len(val) > limit:
                label = key.replace("_", " ").capitalize()
                return Response({"detail": f"{label} is too long (max {limit} characters)."}, status=400)
            setattr(school, key, val)
            fields.append(key)
    logo = request.FILES.get("logo")
    if not logo and fields:
        school.save(update_fields=fields)
        return Response({"motto": school.motto, "principal_name": school.principal_name})
    if not logo:
        return Response({"detail": "Select a PNG, JPG, JPEG, or WEBP logo."}, status=400)
    suffix = Path(logo.name).suffix.lower()
    if suffix not in _ALLOWED or logo.size > _MAX_BYTES:
        return Response({"detail": "Logo must be PNG/JPG/JPEG/WEBP and no larger than 2 MB."}, status=400)
    if getattr(logo, "content_type", "") not in {"image/png", "image/jpeg", "image/webp"}:
        return Response({"detail": "Unsupported image type."}, status=400)
    school.logo = logo
    school.save(update_fields=["logo"] + fields)
    return Response({"logo_url": request.build_absolute_uri(school.logo.url)})
