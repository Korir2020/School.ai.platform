from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from schools.models import Notification


@api_view(["POST"])
def notification_read(request, pk):
    n = Notification.objects.filter(pk=pk, recipient=request.user).first()
    if n is None:
        return Response({"detail": "Not found."}, status=404)
    if n.read_at is None:
        n.read_at = timezone.now()
        n.save(update_fields=["read_at"])
    return Response({"id": n.id, "read": True})


@api_view(["POST"])
def notification_read_all(request):
    count = Notification.objects.filter(
        recipient=request.user, read_at__isnull=True
    ).update(read_at=timezone.now())
    return Response({"marked": count})
