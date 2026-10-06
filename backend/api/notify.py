from schools.models import Notification, SchoolAdminProfile


def _make(school, users, kind, message, join_request):
    Notification.objects.bulk_create([
        Notification(school=school, recipient=u, kind=kind,
                     message=message[:255], join_request=join_request)
        for u in users])


def notify_admins(school, kind, message, join_request=None):
    """One row per admin/deputy of THIS school only."""
    users = [p.user for p in SchoolAdminProfile.objects.filter(
        school=school).select_related("user")]
    _make(school, users, kind, message, join_request)


def notify_user(school, user, kind, message, join_request=None):
    _make(school, [user], kind, message, join_request)


def stored_items(user):
    rows = Notification.objects.filter(recipient=user)
    unread = rows.filter(read_at__isnull=True).count()
    items = [{
        "id": n.id, "kind": n.kind, "message": n.message,
        "timestamp": n.created_at, "read": n.read_at is not None,
        "join_request_id": n.join_request_id} for n in rows[:50]]
    return items, unread
