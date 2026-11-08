"""Shared authorization for private, school-scoped fee data."""

from rest_framework.exceptions import PermissionDenied

from schools.models import SchoolAdminProfile, StaffProfile


_DENIED_DETAIL = "You do not have permission to access fee information."


def get_fee_access_school_id(user, school_id=None):
    """Return the permitted school ID, or raise DRF ``PermissionDenied``.

    Only an authenticated, non-superuser user with a non-deputy
    ``SchoolAdminProfile`` or a ``StaffProfile`` whose role is ``bursar`` may
    access fee data. If ``school_id`` is supplied, the user's permitted role
    must belong to that school. Without it, the user's eligible profiles must
    identify exactly one school, which is returned for queryset scoping.

    All rejected identities and cross-school requests use the same generic
    403 detail; superusers are explicitly denied even if they have a school
    profile.
    """
    if (
        not user
        or not getattr(user, "is_authenticated", False)
        or getattr(user, "is_superuser", False)
    ):
        raise PermissionDenied(_DENIED_DETAIL)

    school_ids = set(
        SchoolAdminProfile.objects.filter(user=user, is_deputy=False)
        .values_list("school_id", flat=True)
    )
    school_ids.update(
        StaffProfile.objects.filter(user=user, role="bursar")
        .values_list("school_id", flat=True)
    )

    if school_id is not None:
        matched = next((allowed_id for allowed_id in school_ids
                        if str(allowed_id) == str(school_id)), None)
        if matched is None:
            raise PermissionDenied(_DENIED_DETAIL)
        return matched

    if len(school_ids) != 1:
        raise PermissionDenied(_DENIED_DETAIL)
    return next(iter(school_ids))
