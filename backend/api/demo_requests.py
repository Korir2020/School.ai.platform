"""Public "Request a demo" form. Stores the request and notifies the team."""
import logging

from django.conf import settings
from django.core.mail import send_mail
from rest_framework import serializers
from rest_framework.decorators import api_view, authentication_classes, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from schools.models import DemoRequest

log = logging.getLogger(__name__)


class DemoRequestThrottle(AnonRateThrottle):
    scope = "demo_request"


class DemoRequestSerializer(serializers.ModelSerializer):
    # Honeypot: real people never see or fill this field.
    website = serializers.CharField(required=False, allow_blank=True, write_only=True)

    class Meta:
        model = DemoRequest
        fields = ["full_name", "email", "phone", "school_name", "role", "learners", "county", "message", "website"]
        extra_kwargs = {"learners": {"min_value": 1, "max_value": 100000}}

    def validate_full_name(self, v):
        v = v.strip()
        if len(v) < 2:
            raise serializers.ValidationError("Enter your full name.")
        return v

    def validate_school_name(self, v):
        v = v.strip()
        if len(v) < 2:
            raise serializers.ValidationError("Enter your school's name.")
        return v

    def validate_phone(self, v):
        v = v.strip()
        if v and not all(c.isdigit() or c in "+ -()" for c in v):
            raise serializers.ValidationError("Use digits, spaces and + only.")
        return v


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([DemoRequestThrottle])
def demo_request_create(request):
    s = DemoRequestSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    if s.validated_data.pop("website", ""):
        return Response({"detail": "Thank you. We will be in touch."}, status=201)
    obj = s.save()
    to = getattr(settings, "DEMO_REQUEST_NOTIFY", "")
    if to:
        try:
            send_mail(
                f"Marian demo request: {obj.school_name}",
                f"{obj.full_name} ({obj.get_role_display()}) <{obj.email}> {obj.phone}\n"
                f"School: {obj.school_name}, {obj.county}\nLearners: {obj.learners or '-'}\n\n{obj.message}",
                settings.DEFAULT_FROM_EMAIL, [to], fail_silently=False,
            )
        except Exception:  # the request is saved; email is best effort
            log.warning("Demo request %s saved but notification email failed", obj.id)
    return Response({"detail": "Thank you. We will contact you within two working days."}, status=201)
