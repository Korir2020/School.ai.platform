"""Persistence for Marian's independent Personalized Learning domain.

These models deliberately do not reference examination, mark, report, fee, or
intervention records. Activity 11 adds account-lifecycle metadata while keeping
identity authorization in Marian's existing user and school-role records.
"""

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, URLValidator
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower
from .quiz_schema import QuizSchemaError, normalize_practice_quiz


def _profile_can_access_item(profile, item):
    """Validate a learning item against the profile's tenant boundary."""
    if item.scope == "public":
        return True
    return (
        profile.account_kind != "public_learner"
        and profile.school_id is not None
        and profile.school_id == item.school_id
    )


class LearningProfile(models.Model):
    """Learning identity without duplicating Marian staff roles.

    `account_kind` describes the data boundary. It is not an authorization role;
    teacher/admin authority must be derived from Marian's server-side profiles.
    """

    ACCOUNT_KINDS = [
        ("school_student", "School-linked student"),
        ("school_member", "School-linked staff member"),
        ("public_learner", "Independent public learner"),
    ]
    AGE_BANDS = [
        ("unknown", "Unknown"),
        ("under_10", "Under 10"),
        ("10_17", "10–17"),
        ("adult", "18 or older"),
    ]
    CONSENT_STATES = [
        ("unknown", "Unknown"),
        ("not_required", "Not required"),
        ("pending", "Pending guardian confirmation"),
        ("verified", "Verified"),
        ("declined", "Declined"),
        ("withdrawn", "Withdrawn"),
    ]
    ACCOUNT_STATUSES = [
        ("active", "Active"),
        ("suspended", "Suspended"),
        ("pending_deletion", "Deletion requested"),
        ("closed", "Closed"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="learning_profile",
    )
    account_kind = models.CharField(max_length=24, choices=ACCOUNT_KINDS)
    school = models.ForeignKey(
        "schools.School", null=True, blank=True, on_delete=models.CASCADE,
        related_name="learning_profiles",
    )
    student = models.OneToOneField(
        "schools.Student", null=True, blank=True, on_delete=models.CASCADE,
        related_name="learning_profile",
    )
    age_band = models.CharField(max_length=12, choices=AGE_BANDS, default="unknown")
    age_verified_at = models.DateTimeField(null=True, blank=True)
    age_verification_source = models.CharField(max_length=24, blank=True, default="")
    contact_verified_at = models.DateTimeField(null=True, blank=True)
    contact_verification_channel = models.CharField(
        max_length=8, blank=True, default="",
        choices=[("", "Not verified"), ("email", "Email"), ("sms", "SMS")],
    )
    consent_state = models.CharField(
        max_length=12, choices=CONSENT_STATES, default="unknown",
    )
    account_status = models.CharField(max_length=20, choices=ACCOUNT_STATUSES, default="active")
    locale = models.CharField(max_length=20, default="en", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(account_kind="public_learner", school__isnull=True, student__isnull=True)
                    | Q(account_kind="school_member", school__isnull=False, student__isnull=True)
                    | Q(account_kind="school_student", school__isnull=False, student__isnull=False)
                ),
                name="learn_profile_scope_valid",
            ),
        ]
        indexes = [models.Index(fields=["school", "account_kind"], name="learn_profile_school_idx")]

    def clean(self):
        super().clean()
        if self.student_id and self.school_id:
            student_school_id = self.student.school_id if hasattr(self, "student") else None
            if student_school_id and student_school_id != self.school_id:
                raise ValidationError({"school": "The linked student belongs to a different school."})

    def __str__(self):
        return f"Learning profile: {self.user_id} ({self.account_kind})"


class LearningInvitation(models.Model):
    """Hashed, one-time invitation metadata; never store the raw claim token."""

    GUARDIAN_STATES = [
        ("not_required", "Not required"),
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ]

    student = models.ForeignKey(
        "schools.Student", on_delete=models.CASCADE, related_name="learning_invitations",
    )
    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="learning_invitations",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="created_learning_invitations",
    )
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    claimed_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    guardian_approval_state = models.CharField(
        max_length=16, choices=GUARDIAN_STATES, default="pending",
    )
    guardian_approved_by = models.ForeignKey(
        "schools.GuardianProfile", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="approved_learning_invitations",
    )
    guardian_approved_at = models.DateTimeField(null=True, blank=True)
    delivery_status = models.CharField(
        max_length=24, default="not_configured",
        choices=[
            ("not_configured", "Delivery not configured"),
            ("manual_handoff_required", "Manual handoff required"),
            ("delivered", "Delivered by verified provider"),
            ("failed", "Provider delivery failed"),
        ],
    )
    delivery_updated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["student"],
                condition=Q(claimed_at__isnull=True, revoked_at__isnull=True),
                name="learn_invite_one_open_student",
            ),
            models.CheckConstraint(
                condition=(
                    Q(guardian_approval_state="approved",
                      guardian_approved_by__isnull=False,
                      guardian_approved_at__isnull=False)
                    | (~Q(guardian_approval_state="approved")
                       & Q(guardian_approved_by__isnull=True,
                           guardian_approved_at__isnull=True))
                ),
                name="learn_invite_guardian_state",
            ),
        ]
        indexes = [
            models.Index(fields=["school", "expires_at"], name="learn_invite_expiry_idx"),
        ]

    def clean(self):
        super().clean()
        if self.student_id and self.school_id:
            student_school_id = self.student.school_id if hasattr(self, "student") else None
            if student_school_id and student_school_id != self.school_id:
                raise ValidationError({"school": "The invited student belongs to a different school."})
        if self.guardian_approved_by_id and self.student_id:
            linked = self.student.guardians.filter(guardian_id=self.guardian_approved_by_id).exists()
            if not linked:
                raise ValidationError({"guardian_approved_by": "This guardian is not linked to the invited student."})

    def __str__(self):
        return f"Learning invitation for student {self.student_id}"


class LearningFramework(models.Model):
    name = models.CharField(max_length=160)
    code = models.SlugField(max_length=50)
    region = models.CharField(max_length=80, blank=True, default="")
    version = models.CharField(max_length=40, blank=True, default="")
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "version"]
        constraints = [
            models.UniqueConstraint(fields=["code", "version"], name="learn_framework_code_version"),
        ]

    def __str__(self):
        return f"{self.name} ({self.version})" if self.version else self.name


class LearningTopic(models.Model):
    NODE_TYPES = [
        ("subject", "Subject"),
        ("topic", "Topic"),
        ("skill", "Skill"),
        ("category", "General knowledge category"),
    ]

    framework = models.ForeignKey(
        LearningFramework, null=True, blank=True, on_delete=models.PROTECT,
        related_name="topics",
    )
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT,
        related_name="children",
    )
    code = models.SlugField(max_length=80)
    name = models.CharField(max_length=160)
    localized_names = models.JSONField(default=dict, blank=True)
    description = models.TextField(blank=True, default="")
    node_type = models.CharField(max_length=16, choices=NODE_TYPES, default="topic")
    grade_min = models.PositiveSmallIntegerField(null=True, blank=True)
    grade_max = models.PositiveSmallIntegerField(null=True, blank=True)
    age_min = models.PositiveSmallIntegerField(null=True, blank=True)
    age_max = models.PositiveSmallIntegerField(null=True, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["framework", "code"], condition=Q(framework__isnull=False),
                name="learn_topic_framework_code",
            ),
            models.UniqueConstraint(
                Lower("code"), condition=Q(framework__isnull=True),
                name="learn_topic_global_code_ci",
            ),
            models.CheckConstraint(
                condition=Q(grade_min__isnull=True) | Q(grade_max__isnull=True) | Q(grade_min__lte=F("grade_max")),
                name="learn_topic_grade_range",
            ),
            models.CheckConstraint(
                condition=Q(age_min__isnull=True) | Q(age_max__isnull=True) | Q(age_min__lte=F("age_max")),
                name="learn_topic_age_range",
            ),
        ]
        indexes = [
            models.Index(fields=["framework", "is_active", "sort_order"], name="learn_topic_browse_idx"),
        ]

    def clean(self):
        super().clean()
        if self.parent_id and self.framework_id:
            parent_framework_id = self.parent.framework_id if hasattr(self, "parent") else None
            if parent_framework_id != self.framework_id:
                raise ValidationError({"parent": "A topic and its parent must use the same framework."})

    def __str__(self):
        return self.name


class LearningResource(models.Model):
    SCOPES = [("public", "Shared catalogue"), ("school", "School-scoped")]
    ORIGINS = [("marian", "Marian-created"), ("external", "External resource")]
    ACCESS_TIERS = [("free", "Free"), ("premium", "Premium")]
    RESOURCE_TYPES = [
        ("lesson", "Lesson"), ("article", "Article"), ("video", "Video"),
        ("audio", "Audio"), ("interactive", "Interactive"),
        ("worksheet", "Worksheet"), ("external_link", "External link"),
        ("other", "Other"),
    ]
    DIFFICULTIES = [("beginner", "Beginner"), ("intermediate", "Intermediate"), ("advanced", "Advanced")]
    STATES = [
        ("draft", "Draft"), ("in_review", "In review"),
        ("changes_requested", "Changes requested"), ("approved", "Approved"),
        ("published", "Published"), ("archived", "Archived"),
    ]

    scope = models.CharField(max_length=10, choices=SCOPES, default="school")
    school = models.ForeignKey(
        "schools.School", null=True, blank=True, on_delete=models.CASCADE,
        related_name="learning_resources",
    )
    title = models.CharField(max_length=240)
    summary = models.TextField(blank=True, default="")
    body = models.TextField(blank=True, default="")
    practice_quiz = models.JSONField(default=dict, blank=True)
    resource_type = models.CharField(max_length=20, choices=RESOURCE_TYPES, default="lesson")
    origin = models.CharField(max_length=12, choices=ORIGINS, default="marian")
    access_tier = models.CharField(max_length=8, choices=ACCESS_TIERS, default="free")
    external_url = models.URLField(
        blank=True, default="", max_length=1000,
        validators=[URLValidator(schemes=["https"])],
    )
    storage_key = models.CharField(max_length=500, blank=True, default="")
    language_code = models.CharField(max_length=20, default="en")
    difficulty = models.CharField(max_length=16, choices=DIFFICULTIES, blank=True, default="")
    age_min = models.PositiveSmallIntegerField(null=True, blank=True)
    age_max = models.PositiveSmallIntegerField(null=True, blank=True)
    frameworks = models.ManyToManyField(LearningFramework, blank=True, related_name="resources")
    topics = models.ManyToManyField(LearningTopic, blank=True, related_name="resources")
    source_name = models.CharField(max_length=240, blank=True, default="")
    license_name = models.CharField(max_length=160, blank=True, default="")
    license_url = models.URLField(blank=True, default="", max_length=1000, validators=[URLValidator(schemes=["https"])] )
    attribution = models.TextField(blank=True, default="")
    rights_notes = models.TextField(blank=True, default="")
    SOURCE_TYPES = [
        ("marian_original", "Marian original"),
        ("teacher_original", "Teacher original"),
        ("open_licensed", "Open licensed"),
        ("public_domain", "Public domain"),
        ("commercial_permission", "Commercial with permission"),
    ]
    source_type = models.CharField(max_length=24, choices=SOURCE_TYPES, blank=True, default="")
    license_expires_on = models.DateField(null=True, blank=True)
    license_verified_at = models.DateTimeField(null=True, blank=True)
    parent = models.ForeignKey(
        "self", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="duplicates",
    )
    license_verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="authored_learning_resources",
    )
    status = models.CharField(max_length=20, choices=STATES, default="draft")
    version = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="reviewed_learning_resources",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    retired_at = models.DateTimeField(null=True, blank=True)
    takedown_reason = models.CharField(max_length=500, blank=True, default="")
    taken_down_at = models.DateTimeField(null=True, blank=True)
    taken_down_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title", "id"]
        constraints = [
            models.CheckConstraint(
                condition=(Q(scope="public", school__isnull=True) | Q(scope="school", school__isnull=False)),
                name="learn_resource_scope_school",
            ),
            models.CheckConstraint(
                condition=Q(age_min__isnull=True) | Q(age_max__isnull=True) | Q(age_min__lte=F("age_max")),
                name="learn_resource_age_range",
            ),
        ]
        indexes = [
            models.Index(fields=["scope", "school", "status"], name="learn_resource_scope_idx"),
            models.Index(fields=["language_code", "status"], name="learn_resource_lang_idx"),
        ]

    def clean(self):
        super().clean()
        try:
            if self.resource_type == "interactive":
                self.practice_quiz = normalize_practice_quiz(
                    self.practice_quiz, allow_incomplete=True,
                )
            elif self.practice_quiz not in ({}, None):
                raise QuizSchemaError("Practice quiz content is only supported for interactive resources.")
        except QuizSchemaError as exc:
            raise ValidationError({"practice_quiz": str(exc)})
        if self.origin == "external" and not self.external_url:
            raise ValidationError({"external_url": "External resources must record an HTTPS source URL."})
        if self.resource_type == "external_link" and not self.external_url:
            raise ValidationError({"external_url": "External links require an HTTPS URL."})
        if self.status == "published" and self.origin == "external" and not self.license_name and not self.rights_notes:
            raise ValidationError({"license_name": "Record the resource licence or documented usage rights before publication."})

    def __str__(self):
        return self.title


class LearningPrivateAsset(models.Model):
    """Private attachment metadata; bytes live in a non-public storage backend."""

    SCAN_STATES = [
        ("quarantined", "Quarantined"),
        ("clean", "Scanner cleared"),
        ("infected", "Scanner detected malware"),
        ("deleted", "Deleted"),
    ]
    CONTENT_TYPES = [
        ("application/pdf", "PDF document"),
        ("image/jpeg", "JPEG image"),
        ("image/png", "PNG image"),
    ]

    resource = models.ForeignKey(
        LearningResource, on_delete=models.CASCADE, related_name="private_assets",
    )
    # A UUID-derived key generated by the server; never returned by an API.
    storage_name = models.CharField(max_length=500, unique=True)
    content_type = models.CharField(max_length=100, choices=CONTENT_TYPES)
    size_bytes = models.PositiveIntegerField()
    sha256 = models.CharField(max_length=64)
    scan_state = models.CharField(max_length=12, choices=SCAN_STATES, default="quarantined")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="uploaded_learning_assets",
    )
    scanned_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["resource", "scan_state"], name="learn_asset_res_scan_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(size_bytes__gt=0), name="learn_asset_size_positive"),
            models.CheckConstraint(
                condition=(Q(scan_state="deleted", deleted_at__isnull=False)
                           | (~Q(scan_state="deleted") & Q(deleted_at__isnull=True))),
                name="learn_asset_deleted_state_time",
            ),
        ]


class LearningResourceTranslation(models.Model):
    REVIEW_STATES = [("draft", "Draft"), ("in_review", "In review"), ("approved", "Approved")]

    resource = models.ForeignKey(
        LearningResource, on_delete=models.CASCADE, related_name="translations",
    )
    language_code = models.CharField(max_length=20)
    title = models.CharField(max_length=240)
    summary = models.TextField(blank=True, default="")
    body = models.TextField(blank=True, default="")
    translation_source = models.CharField(max_length=24, default="human", choices=[("human", "Human"), ("machine_draft", "Machine draft")])
    translator = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="learning_translations",
    )
    review_state = models.CharField(max_length=12, choices=REVIEW_STATES, default="draft")
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="reviewed_learning_translations",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["resource", "language_code"], name="learn_resource_translation_lang"),
        ]

    def clean(self):
        super().clean()
        if self.resource_id and self.language_code == self.resource.language_code:
            raise ValidationError({"language_code": "A translation must use a different language from the original resource."})

    def __str__(self):
        return f"{self.title} [{self.language_code}]"


class LearningPath(models.Model):
    SCOPES = LearningResource.SCOPES
    ORIGINS = [("curated", "Curated"), ("teacher", "Teacher-created"), ("ai_draft", "AI draft")]
    STATES = LearningResource.STATES

    scope = models.CharField(max_length=10, choices=SCOPES, default="school")
    school = models.ForeignKey(
        "schools.School", null=True, blank=True, on_delete=models.CASCADE,
        related_name="learning_paths",
    )
    title = models.CharField(max_length=240)
    description = models.TextField(blank=True, default="")
    objectives = models.JSONField(default=list, blank=True)
    language_code = models.CharField(max_length=20, default="en")
    difficulty = models.CharField(max_length=16, choices=LearningResource.DIFFICULTIES, blank=True, default="")
    access_tier = models.CharField(max_length=8, choices=LearningResource.ACCESS_TIERS, default="free")
    age_min = models.PositiveSmallIntegerField(null=True, blank=True)
    age_max = models.PositiveSmallIntegerField(null=True, blank=True)
    frameworks = models.ManyToManyField(LearningFramework, blank=True, related_name="paths")
    topics = models.ManyToManyField(LearningTopic, blank=True, related_name="paths")
    origin = models.CharField(max_length=12, choices=ORIGINS, default="curated")
    source_name = models.CharField(max_length=240, blank=True, default="")
    license_name = models.CharField(max_length=160, blank=True, default="")
    license_url = models.URLField(
        blank=True, default="", max_length=1000,
        validators=[URLValidator(schemes=["https"])],
    )
    attribution = models.TextField(blank=True, default="")
    rights_notes = models.TextField(blank=True, default="")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="authored_learning_paths",
    )
    status = models.CharField(max_length=20, choices=STATES, default="draft")
    version = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="reviewed_learning_paths",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title", "id"]
        constraints = [
            models.CheckConstraint(
                condition=(Q(scope="public", school__isnull=True) | Q(scope="school", school__isnull=False)),
                name="learn_path_scope_school",
            ),
            models.CheckConstraint(
                condition=Q(age_min__isnull=True) | Q(age_max__isnull=True) | Q(age_min__lte=F("age_max")),
                name="learn_path_age_range",
            ),
        ]
        indexes = [models.Index(fields=["scope", "school", "status"], name="learn_path_scope_idx")]

    def __str__(self):
        return self.title


class LearningPathTranslation(models.Model):
    REVIEW_STATES = [("draft", "Draft"), ("in_review", "In review"), ("approved", "Approved")]

    path = models.ForeignKey(LearningPath, on_delete=models.CASCADE, related_name="translations")
    language_code = models.CharField(max_length=20)
    title = models.CharField(max_length=240)
    description = models.TextField(blank=True, default="")
    objectives = models.JSONField(default=list, blank=True)
    translation_source = models.CharField(
        max_length=24, default="human",
        choices=[("human", "Human"), ("machine_draft", "Machine draft")],
    )
    translator = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="learning_path_translations",
    )
    review_state = models.CharField(max_length=12, choices=REVIEW_STATES, default="draft")
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="reviewed_learning_path_translations",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["path", "language_code"], name="learn_path_translation_lang"),
        ]

    def clean(self):
        super().clean()
        if self.path_id and self.language_code.lower() == self.path.language_code.lower():
            raise ValidationError({"language_code": "A translation must use a different language from the original path."})


class LearningPathItem(models.Model):
    ITEM_TYPES = [("resource", "Resource"), ("activity", "Guided activity"), ("project", "Project")]

    path = models.ForeignKey(LearningPath, on_delete=models.CASCADE, related_name="items")
    position = models.PositiveIntegerField()
    item_type = models.CharField(max_length=12, choices=ITEM_TYPES, default="resource")
    resource = models.ForeignKey(
        LearningResource, null=True, blank=True, on_delete=models.PROTECT,
        related_name="path_items",
    )
    title = models.CharField(max_length=240, blank=True, default="")
    instructions = models.TextField(blank=True, default="")
    completion_rule = models.CharField(max_length=40, blank=True, default="view")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["position", "id"]
        constraints = [
            models.UniqueConstraint(fields=["path", "position"], name="learn_path_item_position"),
            models.CheckConstraint(
                condition=(Q(item_type="resource", resource__isnull=False) | ~Q(item_type="resource")),
                name="learn_path_item_resource",
            ),
        ]

    def clean(self):
        super().clean()
        if self.path_id and self.resource_id:
            path = self.path
            resource = self.resource
            if path.scope == "public" and resource.scope != "public":
                raise ValidationError({"resource": "A shared path cannot contain school-private resources."})
            if path.scope == "school" and resource.scope == "school" and path.school_id != resource.school_id:
                raise ValidationError({"resource": "A path cannot contain another school's private resource."})

    def __str__(self):
        return self.title or (self.resource.title if self.resource_id else f"Step {self.position}")


class LearningPreference(models.Model):
    profile = models.OneToOneField(
        LearningProfile, on_delete=models.CASCADE, related_name="preferences",
    )
    topics = models.ManyToManyField(LearningTopic, blank=True, related_name="interested_profiles")
    preferred_languages = models.JSONField(default=list, blank=True)
    preferred_formats = models.JSONField(default=list, blank=True)
    preferred_difficulty = models.CharField(
        max_length=16, choices=[("", "Not specified"), *LearningResource.DIFFICULTIES], blank=True, default="",
    )
    recommendations_enabled = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Learning preferences for profile {self.profile_id}"


class LearningGoal(models.Model):
    STATES = [("active", "Active"), ("completed", "Completed"), ("paused", "Paused"), ("closed", "Closed")]

    profile = models.ForeignKey(LearningProfile, on_delete=models.CASCADE, related_name="goals")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    topic = models.ForeignKey(
        LearningTopic, null=True, blank=True, on_delete=models.SET_NULL, related_name="goals",
    )
    path = models.ForeignKey(
        LearningPath, null=True, blank=True, on_delete=models.SET_NULL, related_name="goals",
    )
    target_date = models.DateField(null=True, blank=True)
    state = models.CharField(max_length=12, choices=STATES, default="active")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["state", "target_date", "created_at"]
        indexes = [models.Index(fields=["profile", "state"], name="learn_goal_profile_state_idx")]

    def clean(self):
        super().clean()
        if self.profile_id and self.path_id and not _profile_can_access_item(self.profile, self.path):
            raise ValidationError({"path": "The learning path is outside this profile's scope."})

    def __str__(self):
        return self.title


class SavedLearningItem(models.Model):
    profile = models.ForeignKey(LearningProfile, on_delete=models.CASCADE, related_name="saved_items")
    resource = models.ForeignKey(
        LearningResource, null=True, blank=True, on_delete=models.PROTECT,
        related_name="saved_by_profiles",
    )
    path = models.ForeignKey(
        LearningPath, null=True, blank=True, on_delete=models.PROTECT,
        related_name="saved_by_profiles",
    )
    saved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-saved_at"]
        constraints = [
            models.CheckConstraint(
                condition=(Q(resource__isnull=False, path__isnull=True) | Q(resource__isnull=True, path__isnull=False)),
                name="learn_saved_exactly_one_item",
            ),
            models.UniqueConstraint(
                fields=["profile", "resource"], condition=Q(resource__isnull=False),
                name="learn_saved_profile_resource",
            ),
            models.UniqueConstraint(
                fields=["profile", "path"], condition=Q(path__isnull=False),
                name="learn_saved_profile_path",
            ),
        ]

    def clean(self):
        super().clean()
        if self.resource_id and self.path_id:
            raise ValidationError("Save either one resource or one path, not both.")
        item = self.resource if self.resource_id else self.path if self.path_id else None
        if self.profile_id and item and not _profile_can_access_item(self.profile, item):
            raise ValidationError("The saved item is outside this profile's scope.")


class LearningActivityEvent(models.Model):
    EVENT_TYPES = [
        ("started", "Started"), ("progress", "Progress"),
        ("completed", "Completed"), ("submitted", "Submitted work"),
        ("feedback", "Feedback"),
    ]

    profile = models.ForeignKey(LearningProfile, on_delete=models.CASCADE, related_name="activity_events")
    event_type = models.CharField(max_length=12, choices=EVENT_TYPES)
    resource = models.ForeignKey(
        LearningResource, null=True, blank=True, on_delete=models.PROTECT,
        related_name="activity_events",
    )
    path_item = models.ForeignKey(
        LearningPathItem, null=True, blank=True, on_delete=models.PROTECT,
        related_name="activity_events",
    )
    occurred_at = models.DateTimeField()
    idempotency_key = models.UUIDField(default=uuid.uuid4)
    duration_seconds = models.PositiveIntegerField(
        null=True, blank=True, validators=[MaxValueValidator(86400)],
    )
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-occurred_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["profile", "idempotency_key"], name="learn_event_idempotency"),
            models.CheckConstraint(
                condition=Q(resource__isnull=False) | Q(path_item__isnull=False),
                name="learn_event_requires_target",
            ),
        ]
        indexes = [
            models.Index(fields=["profile", "occurred_at"], name="learn_event_profile_time_idx"),
            models.Index(fields=["event_type", "occurred_at"], name="learn_event_type_time_idx"),
        ]

    def clean(self):
        super().clean()
        if not self.resource_id and not self.path_item_id:
            raise ValidationError("A learning activity event must identify a resource or path item.")
        if not self.profile_id:
            return
        profile = self.profile
        if self.resource_id and not _profile_can_access_item(profile, self.resource):
            raise ValidationError({"resource": "The resource is outside this profile's scope."})
        if self.path_item_id and not _profile_can_access_item(profile, self.path_item.path):
            raise ValidationError({"path_item": "The path item is outside this profile's scope."})


class LearningQuizAttempt(models.Model):
    """Private, version-bound quiz outcome; raw learner answers are not retained."""

    profile = models.ForeignKey(
        LearningProfile, on_delete=models.CASCADE, related_name="quiz_attempts",
    )
    resource = models.ForeignKey(
        LearningResource, on_delete=models.PROTECT, related_name="quiz_attempts",
    )
    resource_version = models.PositiveIntegerField()
    idempotency_key = models.UUIDField()
    request_fingerprint = models.CharField(max_length=64)
    question_count = models.PositiveSmallIntegerField()
    correct_count = models.PositiveSmallIntegerField()
    feedback = models.JSONField(default=list)
    completed_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-completed_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["profile", "idempotency_key"],
                name="learn_quiz_profile_idempotency",
            ),
            models.CheckConstraint(
                condition=Q(question_count__gt=0, correct_count__lte=F("question_count")),
                name="learn_quiz_attempt_counts_valid",
            ),
        ]
        indexes = [models.Index(fields=["profile", "completed_at"], name="learn_quiz_profile_time_idx")]

    def clean(self):
        super().clean()
        if self.profile_id and self.resource_id:
            if self.resource.resource_type != "interactive":
                raise ValidationError({"resource": "Quiz attempts must reference an interactive resource."})
            if not _profile_can_access_item(self.profile, self.resource):
                raise ValidationError({"resource": "The resource is outside this learner profile's scope."})


class LearningPathParticipation(models.Model):
    """A learner's private participation in one published path version."""

    STATES = [("in_progress", "In progress"), ("completed", "Completed")]

    profile = models.ForeignKey(
        LearningProfile, on_delete=models.CASCADE, related_name="path_participations",
    )
    path = models.ForeignKey(
        LearningPath, on_delete=models.PROTECT, related_name="participations",
    )
    path_version = models.PositiveIntegerField()
    state = models.CharField(max_length=16, choices=STATES, default="in_progress")
    started_at = models.DateTimeField(auto_now_add=True)
    last_activity_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["profile", "path", "path_version"],
                name="learn_participation_profile_path_ver",
            ),
            models.CheckConstraint(
                condition=(
                    Q(state="completed", completed_at__isnull=False)
                    | (Q(state="in_progress") & Q(completed_at__isnull=True))
                ),
                name="learn_participation_state_time",
            ),
        ]
        indexes = [
            models.Index(fields=["profile", "started_at"], name="learn_particip_profile_idx"),
        ]


class LearningContentRevision(models.Model):
    """Immutable, access-controlled snapshots of learning content changes."""

    resource = models.ForeignKey(
        LearningResource, null=True, blank=True, on_delete=models.CASCADE,
        related_name="content_revisions",
    )
    path = models.ForeignKey(
        LearningPath, null=True, blank=True, on_delete=models.CASCADE,
        related_name="content_revisions",
    )
    version = models.PositiveIntegerField()
    snapshot = models.JSONField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="learning_content_revisions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-version", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(resource__isnull=False, path__isnull=True)
                    | Q(resource__isnull=True, path__isnull=False)
                ),
                name="learn_revision_exactly_one_target",
            ),
            models.UniqueConstraint(
                fields=["resource", "version"], condition=Q(resource__isnull=False),
                name="learn_revision_resource_version",
            ),
            models.UniqueConstraint(
                fields=["path", "version"], condition=Q(path__isnull=False),
                name="learn_revision_path_version",
            ),
        ]


class LearningProject(models.Model):
    SCOPES = LearningResource.SCOPES
    REVIEW_STATES = [("not_submitted", "Not submitted"), ("submitted", "Submitted"), ("reviewed", "Reviewed")]

    owner = models.ForeignKey(LearningProfile, on_delete=models.CASCADE, related_name="projects")
    scope = models.CharField(max_length=10, choices=SCOPES)
    school = models.ForeignKey(
        "schools.School", null=True, blank=True, on_delete=models.CASCADE,
        related_name="learning_projects",
    )
    title = models.CharField(max_length=240)
    objective = models.TextField(blank=True, default="")
    topic = models.ForeignKey(
        LearningTopic, null=True, blank=True, on_delete=models.SET_NULL, related_name="projects",
    )
    age_band = models.CharField(max_length=12, choices=LearningProfile.AGE_BANDS, default="unknown")
    stage_template = models.JSONField(default=list, blank=True)
    review_state = models.CharField(max_length=16, choices=REVIEW_STATES, default="not_submitted")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "id"]
        constraints = [
            models.CheckConstraint(
                condition=(Q(scope="public", school__isnull=True) | Q(scope="school", school__isnull=False)),
                name="learn_project_scope_school",
            ),
        ]
        indexes = [models.Index(fields=["owner", "updated_at"], name="learn_project_owner_time_idx")]

    def clean(self):
        super().clean()
        if self.owner_id:
            owner = self.owner
            if owner.account_kind == "public_learner":
                if self.scope != "public" or self.school_id is not None:
                    raise ValidationError({"scope": "Public learner projects must remain in the public scope."})
            elif self.scope != "school" or self.school_id != owner.school_id:
                raise ValidationError({"school": "School member projects must remain within the profile's school."})

    def __str__(self):
        return self.title


class LearningProjectWork(models.Model):
    project = models.ForeignKey(LearningProject, on_delete=models.CASCADE, related_name="work_items")
    learner = models.ForeignKey(LearningProfile, on_delete=models.CASCADE, related_name="project_work")
    stage = models.CharField(max_length=80, blank=True, default="")
    text_content = models.TextField(blank=True, default="")
    private_storage_key = models.CharField(max_length=500, blank=True, default="")
    submitted_at = models.DateTimeField(null=True, blank=True)
    review_state = models.CharField(
        max_length=16,
        choices=[("draft", "Draft"), ("submitted", "Submitted"), ("reviewed", "Reviewed")],
        default="draft",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="reviewed_learning_project_work",
    )
    review_feedback = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["learner", "created_at"], name="learn_work_learner_time_idx")]

    def clean(self):
        super().clean()
        if self.project_id and self.learner_id and self.project.owner_id != self.learner_id:
            raise ValidationError({"learner": "Project work must belong to the project owner."})


class LearningRecommendation(models.Model):
    STATES = [("shown", "Shown"), ("accepted", "Accepted"), ("dismissed", "Dismissed"), ("expired", "Expired")]

    profile = models.ForeignKey(LearningProfile, on_delete=models.CASCADE, related_name="recommendations")
    resource = models.ForeignKey(
        LearningResource, null=True, blank=True, on_delete=models.PROTECT,
        related_name="recommendations",
    )
    path = models.ForeignKey(
        LearningPath, null=True, blank=True, on_delete=models.PROTECT,
        related_name="recommendations",
    )
    reason_code = models.CharField(max_length=48)
    explanation = models.CharField(max_length=500, blank=True, default="")
    # Store only allowlisted learning signals; never examination/report data or raw prompts.
    source_signals = models.JSONField(default=list, blank=True)
    algorithm_version = models.CharField(max_length=40, default="rules-v1")
    state = models.CharField(max_length=12, choices=STATES, default="shown")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=(Q(resource__isnull=False, path__isnull=True) | Q(resource__isnull=True, path__isnull=False)),
                name="learn_recommendation_one_item",
            ),
            models.UniqueConstraint(
                fields=["profile", "resource"],
                condition=Q(resource__isnull=False, reason_code="personalized_rules", algorithm_version="rules-v1", state__in=["shown", "accepted"]),
                name="learn_auto_reco_res_active",
            ),
            models.UniqueConstraint(
                fields=["profile", "path"],
                condition=Q(path__isnull=False, reason_code="personalized_rules", algorithm_version="rules-v1", state__in=["shown", "accepted"]),
                name="learn_auto_reco_path_active",
            ),
        ]
        indexes = [models.Index(fields=["profile", "state", "created_at"], name="learn_reco_profile_state_idx")]

    def clean(self):
        super().clean()
        if self.resource_id and self.path_id:
            raise ValidationError("A recommendation must target exactly one resource or path.")
        item = self.resource if self.resource_id else self.path if self.path_id else None
        if self.profile_id and item and not _profile_can_access_item(self.profile, item):
            raise ValidationError("The recommended item is outside this profile's scope.")


class AIInteraction(models.Model):
    """Usage metadata only; raw learner prompts/responses are intentionally absent."""

    PURPOSES = [("tutor", "Tutor"), ("content_draft", "Content draft"), ("translation", "Translation"), ("recommendation", "Recommendation")]
    STATES = [("reserved", "Reserved"), ("succeeded", "Succeeded"), ("failed", "Failed"), ("blocked", "Blocked")]

    profile = models.ForeignKey(LearningProfile, on_delete=models.CASCADE, related_name="ai_interactions")
    purpose = models.CharField(max_length=20, choices=PURPOSES)
    provider = models.CharField(max_length=80, blank=True, default="")
    model_name = models.CharField(max_length=120, blank=True, default="")
    policy_version = models.CharField(max_length=40, blank=True, default="")
    state = models.CharField(max_length=12, choices=STATES, default="reserved")
    request_id = models.CharField(max_length=120, blank=True, default="")
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    estimated_cost = models.DecimalField(
        max_digits=12, decimal_places=6, default=0,
        validators=[MinValueValidator(0)],
    )
    latency_ms = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["profile", "created_at"], name="learn_ai_profile_time_idx"),
            models.Index(fields=["provider", "created_at"], name="learn_ai_provider_time_idx"),
        ]


class LearningMotivationSettings(models.Model):
    """Learner-controlled motivation preferences; no public leaderboard data."""
    profile = models.OneToOneField(LearningProfile, on_delete=models.CASCADE, related_name="motivation_settings")
    enabled = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)


class LearningOfflinePackage(models.Model):
    """A revocable, time-limited manifest for encrypted local learning content.

    Content is encrypted in the learner's browser; the server stores only the
    manifest, opaque device identifier, expiry and revocation state.
    """
    profile = models.ForeignKey(LearningProfile, on_delete=models.CASCADE, related_name="offline_packages")
    package_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    device_id = models.CharField(max_length=128)
    manifest = models.JSONField(default=dict)
    issued_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-issued_at"]
        indexes = [models.Index(fields=["profile", "expires_at"], name="learn_offline_profile_exp_idx")]


class LearningOfflineOperation(models.Model):
    """Idempotent offline event receipt with explicit conflict state."""
    STATES = [("synced", "Synced"), ("conflict", "Conflict")]
    package = models.ForeignKey(LearningOfflinePackage, on_delete=models.CASCADE, related_name="operations")
    operation_id = models.UUIDField()
    event_type = models.CharField(max_length=12)
    payload = models.JSONField(default=dict)
    state = models.CharField(max_length=10, choices=STATES)
    conflict_code = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["package", "operation_id"], name="learn_offline_op_unique")]
        indexes = [models.Index(fields=["package", "state"], name="learn_offline_op_state_idx")]


class LearningAuditEvent(models.Model):
    """Minimal metadata for privileged learning-domain actions; avoid raw PII."""

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="learning_audit_events",
    )
    school = models.ForeignKey(
        "schools.School", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="learning_audit_events",
    )
    scope = models.CharField(max_length=10, choices=LearningResource.SCOPES)
    action = models.CharField(max_length=64)
    target_type = models.CharField(max_length=80, blank=True, default="")
    target_id = models.CharField(max_length=80, blank=True, default="")
    safe_details = models.JSONField(default=dict, blank=True)
    occurred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-occurred_at"]
        indexes = [
            models.Index(fields=["school", "occurred_at"], name="learn_audit_school_time_idx"),
            models.Index(fields=["scope", "occurred_at"], name="learn_audit_scope_time_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(Q(scope="public", school__isnull=True) | Q(scope="school", school__isnull=False)),
                name="learn_audit_scope_school",
            ),
        ]

    def clean(self):
        super().clean()
        if self.scope == "public" and self.school_id:
            raise ValidationError({"school": "Public-scope audit events must not be attributed to a school."})
        if self.scope == "school" and not self.school_id:
            raise ValidationError({"school": "School-scope audit events must include the school."})


class LearningGuardianRelationship(models.Model):
    """Provider-verified guardian link for independent learners; no self-approval."""

    STATUSES = [
        ("pending", "Pending verification"),
        ("verified", "Verified and consented"),
        ("rejected", "Rejected"),
        ("withdrawn", "Consent withdrawn"),
    ]
    RELATIONSHIPS = [
        ("parent", "Parent"),
        ("legal_guardian", "Legal guardian"),
        ("other", "Other approved guardian"),
    ]

    learner = models.ForeignKey(
        LearningProfile, on_delete=models.CASCADE, related_name="guardian_relationships",
    )
    guardian = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="learning_guardian_relationships",
    )
    relationship = models.CharField(max_length=16, choices=RELATIONSHIPS)
    status = models.CharField(max_length=12, choices=STATUSES, default="pending")
    verification_provider = models.CharField(max_length=80, blank=True, default="")
    identity_verified_at = models.DateTimeField(null=True, blank=True)
    consent_at = models.DateTimeField(null=True, blank=True)
    consent_version = models.CharField(max_length=40, blank=True, default="")
    consent_withdrawn_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["learner", "guardian"], name="learn_guardian_link_unique"),
            models.CheckConstraint(
                condition=(
                    Q(status="verified", identity_verified_at__isnull=False,
                      consent_at__isnull=False, consent_withdrawn_at__isnull=True)
                    | Q(status="withdrawn", consent_withdrawn_at__isnull=False)
                    | Q(status__in=["pending", "rejected"])
                ),
                name="learn_guardian_link_state_valid",
            ),
        ]
        indexes = [models.Index(fields=["guardian", "status"], name="learn_guardian_user_state_idx")]

    def clean(self):
        super().clean()
        if self.learner_id and self.learner.account_kind != "public_learner":
            raise ValidationError({"learner": "Independent guardian links are only for public learners."})
        if self.learner_id and self.guardian_id == self.learner.user_id:
            raise ValidationError({"guardian": "A learner cannot verify their own guardian relationship."})


class LearningAccountLifecycleRequest(models.Model):
    """Auditable request only; permanent deletion waits for an approved retention process."""

    REQUEST_TYPES = [("deletion", "Deletion"), ("suspension", "Suspension")]
    REASONS = [
        ("self_requested", "Account owner requested"),
        ("guardian_request", "Verified guardian requested"),
        ("privacy_request", "Privacy request"),
        ("security", "Security or safeguarding"),
    ]
    STATUSES = [
        ("pending", "Pending review"),
        ("approved", "Approved; execution still policy-gated"),
        ("rejected", "Rejected"),
        ("cancelled", "Cancelled"),
    ]

    profile = models.ForeignKey(
        LearningProfile, on_delete=models.PROTECT, related_name="lifecycle_requests",
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="learning_lifecycle_requests",
    )
    request_type = models.CharField(max_length=12, choices=REQUEST_TYPES)
    reason_code = models.CharField(max_length=24, choices=REASONS, default="self_requested")
    status = models.CharField(max_length=12, choices=STATUSES, default="pending")
    previous_account_status = models.CharField(max_length=20, choices=LearningProfile.ACCOUNT_STATUSES, default="active")
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="resolved_learning_lifecycle_requests",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["profile", "request_type"], condition=Q(status="pending"),
                name="learn_lifecycle_one_pending",
            ),
        ]
        indexes = [models.Index(fields=["status", "created_at"], name="learn_lifecycle_review_idx")]


class LearningSubscriptionPlan(models.Model):
    """Individually billed plan; intentionally separate from school fee records."""

    TIERS = [("free", "Free"), ("premium", "Premium")]
    INTERVALS = [("none", "No recurring billing"), ("monthly", "Monthly"), ("yearly", "Yearly")]

    code = models.SlugField(max_length=40, unique=True)
    name = models.CharField(max_length=100)
    tier = models.CharField(max_length=12, choices=TIERS)
    description = models.CharField(max_length=500, blank=True, default="")
    amount = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0)],
    )
    currency = models.CharField(max_length=3, blank=True, default="")
    billing_interval = models.CharField(max_length=10, choices=INTERVALS, default="none")
    entitlements = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["tier", "code"]

    def clean(self):
        super().clean()
        if self.tier == "free":
            if self.amount not in (None, 0):
                raise ValidationError({"amount": "The free plan cannot have a charge."})
            if self.billing_interval != "none":
                raise ValidationError({"billing_interval": "The free plan cannot recur."})
        if self.tier == "premium" and self.is_active:
            if (
                self.amount is None or self.amount <= 0
                or len(self.currency) != 3 or not self.currency.isascii()
                or not self.currency.isalpha() or not self.currency.isupper()
            ):
                raise ValidationError({"is_active": "Premium activation requires an approved price and ISO currency."})
            if self.billing_interval == "none":
                raise ValidationError({"billing_interval": "An active premium plan requires a billing interval."})

    def __str__(self):
        return f"{self.name} ({self.code})"


class LearningSubscription(models.Model):
    """Subscription history for one learner profile, independent of school billing."""

    STATUSES = [
        ("pending", "Pending provider confirmation"),
        ("active", "Active"),
        ("past_due", "Payment past due"),
        ("cancelled", "Cancelled"),
        ("expired", "Expired"),
    ]

    profile = models.ForeignKey(
        LearningProfile, on_delete=models.PROTECT, related_name="subscriptions",
    )
    plan = models.ForeignKey(
        LearningSubscriptionPlan, on_delete=models.PROTECT, related_name="subscriptions",
    )
    payer = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
        related_name="learning_subscriptions_paid",
    )
    status = models.CharField(max_length=12, choices=STATUSES, default="pending")
    provider = models.CharField(max_length=80, blank=True, default="")
    provider_subscription_id = models.CharField(max_length=160, blank=True, default="")
    current_period_start = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    cancel_at_period_end = models.BooleanField(default=False)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "provider_subscription_id"],
                condition=~Q(provider_subscription_id=""),
                name="learn_sub_provider_ref_unique",
            ),
        ]
        indexes = [models.Index(fields=["profile", "status"], name="learn_sub_profile_state_idx")]


class LearningPaymentTransaction(models.Model):
    """Provider event ledger; never stores card data or unverified success."""

    STATUSES = [
        ("pending", "Pending"),
        ("succeeded", "Verified success"),
        ("failed", "Failed"),
        ("refunded", "Refunded"),
    ]

    subscription = models.ForeignKey(
        LearningSubscription, on_delete=models.PROTECT, related_name="transactions",
    )
    payer = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
        related_name="learning_payment_transactions",
    )
    provider = models.CharField(max_length=80)
    provider_event_id = models.CharField(max_length=160)
    provider_transaction_id = models.CharField(max_length=160, blank=True, default="")
    status = models.CharField(max_length=12, choices=STATUSES, default="pending")
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    currency = models.CharField(max_length=3)
    provider_verified_at = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-received_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "provider_event_id"],
                name="learn_payment_event_unique",
            ),
            models.CheckConstraint(
                condition=(~Q(status="succeeded") | Q(provider_verified_at__isnull=False)),
                name="learn_payment_success_verified",
            ),
        ]
        indexes = [models.Index(fields=["subscription", "status"], name="learn_payment_sub_state_idx")]


class LearningSchoolSettings(models.Model):
    """School-owned controls for Learning, separate from academic records."""

    school = models.OneToOneField(
        "schools.School", on_delete=models.CASCADE,
        related_name="learning_settings",
    )
    learning_access_enabled = models.BooleanField(default=True)
    teacher_studio_enabled = models.BooleanField(default=True)
    teacher_recommendations_enabled = models.BooleanField(default=False)
    minimum_learner_age = models.PositiveSmallIntegerField(default=0)
    maximum_learner_age = models.PositiveSmallIntegerField(default=120)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="updated_learning_school_settings",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(minimum_learner_age__lte=F("maximum_learner_age")),
                name="learn_school_age_range_valid",
            ),
            models.CheckConstraint(
                condition=Q(maximum_learner_age__lte=120),
                name="learn_school_age_max_plausible",
            ),
            models.CheckConstraint(
                condition=Q(minimum_learner_age__lte=120),
                name="learn_school_age_min_plausible",
            ),
        ]

    def clean(self):
        super().clean()
        if self.minimum_learner_age > self.maximum_learner_age:
            raise ValidationError({"minimum_learner_age": "Minimum learner age must not exceed maximum learner age."})
        if self.maximum_learner_age > 120:
            raise ValidationError({"maximum_learner_age": "Maximum learner age must be 120 or less."})


class LearningContentRole(models.Model):
    """Marian-wide content role; never implied by staff or superuser."""

    AUTHOR = "author"
    CURATOR = "curator"
    ROLES = [(AUTHOR, "Marian author"), (CURATOR, "Marian curator")]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="learning_content_roles",
    )
    role = models.CharField(max_length=10, choices=ROLES)
    is_active = models.BooleanField(default=True)
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="learning_content_roles_granted",
    )
    granted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "role"], name="learn_content_role_unique"
            ),
        ]


class LearningQuestion(models.Model):
    """One practice question, kept in step with the quiz JSON of its resource."""

    resource = models.ForeignKey(LearningResource, on_delete=models.CASCADE, related_name="bank_questions")
    question_key = models.CharField(max_length=40)
    position = models.PositiveSmallIntegerField(default=0)
    prompt = models.CharField(max_length=500)
    options = models.JSONField(default=list)
    correct_option_id = models.CharField(max_length=40)
    explanation = models.CharField(max_length=600, blank=True, default="")
    topics = models.ManyToManyField(LearningTopic, blank=True, related_name="bank_questions")
    difficulty = models.CharField(max_length=16, choices=LearningResource.DIFFICULTIES, blank=True, default="")
    language_code = models.CharField(max_length=20, default="en")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["resource_id", "position", "id"]
        constraints = [
            models.UniqueConstraint(fields=["resource", "question_key"], name="learning_question_unique_key"),
        ]

    def __str__(self):
        return f"{self.resource_id}:{self.question_key}"


from django.db.models.signals import post_save as _post_save  # noqa: E402
from .question_bank import sync_resource_questions as _sync_bank  # noqa: E402


def _bank_after_save(sender, instance, raw=False, **kwargs):
    if not raw:
        _sync_bank(instance)


_post_save.connect(_bank_after_save, sender=LearningResource, dispatch_uid="learning_question_bank_sync")
