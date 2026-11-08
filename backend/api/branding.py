from pathlib import Path

from django.conf import settings
from PIL import Image, UnidentifiedImageError
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response

from schools.models import SchoolAdminProfile
from .views import _scope

_ALLOWED = {".png", ".jpg", ".jpeg", ".webp"}
_MAX_BYTES = 2 * 1024 * 1024
_FORMATS = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".webp": "WEBP"}
_CONTENT_TYPES = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}


def _validate_logo(logo):
    suffix = Path(logo.name or "").suffix.lower()
    if suffix not in _ALLOWED:
        return "Logo must be PNG/JPG/JPEG/WEBP and no larger than 2 MB."
    if logo.size > _MAX_BYTES:
        return "Logo must be PNG/JPG/JPEG/WEBP and no larger than 2 MB."
    expected = _FORMATS[suffix]
    declared = (getattr(logo, "content_type", "") or "").lower()
    if declared and declared != _CONTENT_TYPES[expected]:
        return "The uploaded content type does not match the logo extension."
    try:
        logo.seek(0)
        image = Image.open(logo)
        detected = image.format
        image.verify()
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError, ValueError):
        return "The logo is not a readable PNG, JPG, JPEG, or WEBP image."
    finally:
        logo.seek(0)
    if detected != expected:
        return "The file extension does not match the image type."
    return None


@api_view(["GET", "POST", "DELETE"])
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
    if request.method == "DELETE":
        if school.logo:
            school.logo.delete(save=False)
        school.logo = None
        school.save(update_fields=["logo"])
        return Response({"logo_url": None})
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
    problem = _validate_logo(logo)
    if problem:
        return Response({"detail": problem}, status=400)
    old_name = school.logo.name if school.logo else None
    school.logo = logo
    school.save(update_fields=["logo"] + fields)
    new_name = school.logo.name
    if old_name and old_name != new_name:
        school.logo.storage.delete(old_name)
    return Response({"logo_url": request.build_absolute_uri(school.logo.url)})
