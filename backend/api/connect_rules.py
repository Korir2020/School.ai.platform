from django.db import IntegrityError
from django.db.models import Q
from django.db.models.functions import Lower

from api import connect_guard as g
from schools.models import (
    ConnectChannel,
    ConnectMute,
    Enrollment,
    GuardianProfile,
    SchoolAdminProfile,
    Student,
    StudentGuardian,
    TeacherProfile,
)

ADMIN, TEACHER, PARENT = "admin", "teacher", "parent"
MAX_POST = 2000
DEFAULT_CHANNELS = [
    ("School Notices", "Official notices from the school. Only school administrators post here.", "notices"),
    ("Parents Community", "Introductions and discussion between parents and staff.", "community"),
]
ROLE_LABEL = {ADMIN: "School admin", TEACHER: "Teacher", PARENT: "Parent"}


class ConnectError(Exception):
    pass


def linked_children(guardian):
    linked = StudentGuardian.objects.filter(guardian=guardian).values("student_id")
    active = Enrollment.objects.filter(student_id__in=linked, is_active=True).values("student_id")
    return Student.objects.filter(school_id=guardian.school_id, id__in=active)


def membership(user):
    """Return (school_id, role) for a Connect member, or (None, None)."""
    if not user or not user.is_authenticated:
        return None, None
    admin = SchoolAdminProfile.objects.filter(user=user).first()
    if admin:
        return admin.school_id, ADMIN
    teacher = TeacherProfile.objects.filter(user=user).first()
    if teacher:
        return teacher.school_id, TEACHER
    guardian = GuardianProfile.objects.filter(user=user).first()
    if guardian and linked_children(guardian).exists():
        return guardian.school_id, PARENT
    return None, None


def ensure_default_channels(school_id):
    for name, description, kind in DEFAULT_CHANNELS:
        try:
            ConnectChannel.objects.get_or_create(
                school_id=school_id,
                name=name,
                defaults={"description": description, "kind": kind, "is_default": True},
            )
        except IntegrityError:
            pass


def can_post(channel, role):
    if channel.kind == "notices":
        return role == ADMIN
    return role in (ADMIN, TEACHER, PARENT)


def is_muted(school_id, user):
    return ConnectMute.objects.filter(school_id=school_id, user=user).exists()


def roles_for(user_ids):
    ids = {i for i in user_ids if i}
    out = {}
    for uid in TeacherProfile.objects.filter(user_id__in=ids).values_list("user_id", flat=True):
        out[uid] = TEACHER
    for uid in SchoolAdminProfile.objects.filter(user_id__in=ids).values_list("user_id", flat=True):
        out[uid] = ADMIN
    for uid in ids:
        out.setdefault(uid, PARENT)
    return out


def display_name(user, role):
    """Never falls back to the username, because usernames can be phone numbers or emails."""
    name = (user.get_full_name() or "").strip() if user else ""
    return name or ROLE_LABEL.get(role, "Member")


def check_text(school_id, role, user, text):
    text = (text or "").strip()
    if not text:
        raise ConnectError("Write a message first.")
    if len(text) > MAX_POST:
        raise ConnectError("The message is too long (2000 characters at most).")
    if role != ADMIN:
        if g.has_phone(text):
            raise ConnectError("Phone numbers cannot be shared in Connect. Please remove the number.")
        if g.has_email(text):
            raise ConnectError("Email addresses cannot be shared in Connect. Please remove the address.")
    tokens = g.id_tokens(text)
    if tokens:
        found = (
            Student.objects.annotate(adm_l=Lower("admission_number"))
            .filter(school_id=school_id, adm_l__in=tokens)
            .exists()
        )
        if found:
            raise ConnectError("Admission numbers cannot be shared in Connect. Please remove the number.")
    if role == PARENT:
        _check_other_learners(school_id, user, text)
    return text


def _check_other_learners(school_id, user, text):
    seq = g.name_words(text)
    words = sorted({w for w in seq if len(w) >= 2})[:60]
    if not words:
        return
    own = set()
    guardian = GuardianProfile.objects.filter(user=user, school_id=school_id).first()
    if guardian:
        own = set(linked_children(guardian).values_list("id", flat=True))
    q = Q()
    for w in words:
        q |= Q(last_name__icontains=w)
    for s in Student.objects.filter(school_id=school_id).filter(q):
        if s.id in own:
            continue
        if g.mentions_name(seq, s.first_name, s.last_name):
            raise ConnectError("Please do not write other learners' names. You can mention your own child.")
