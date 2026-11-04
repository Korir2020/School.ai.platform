from schools.models import Notification, SchoolAdminProfile

from .alerts import notify


def notify_admins(school, kind, message, join_request=None):
    """One row per admin/deputy of THIS school only, plus an email copy
    for admins who have an address and have not turned email alerts off."""
    users = [p.user for p in SchoolAdminProfile.objects.filter(
        school=school).select_related("user")]
    notify(school, users, kind, message, join_request)


def notify_user(school, user, kind, message, join_request=None):
    notify(school, [user], kind, message, join_request)


def stored_items(user):
    rows = Notification.objects.filter(recipient=user)
    unread = rows.filter(read_at__isnull=True).count()
    items = [{
        "id": n.id, "kind": n.kind, "message": n.message,
        "timestamp": n.created_at, "read": n.read_at is not None,
        "join_request_id": n.join_request_id} for n in rows[:50]]
    return items, unread
