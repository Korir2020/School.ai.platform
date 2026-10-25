from django.conf import settings
from django.db import models
from django.db.models.functions import Lower
from django.core.validators import MinValueValidator, MaxValueValidator


class School(models.Model):
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50, unique=True)
    location = models.CharField(max_length=200, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    school_type = models.CharField(max_length=30, blank=True)
    county = models.CharField(max_length=100, blank=True)
    sub_county = models.CharField(max_length=100, blank=True)
    logo = models.FileField(upload_to="school-logos/", null=True, blank=True)
    motto = models.CharField(max_length=200, blank=True, default="")
    principal_name = models.CharField(max_length=100, blank=True, default="")
    setup_completed_at = models.DateTimeField(null=True, blank=True)
    is_suspended = models.BooleanField(default=False)
    suspended_at = models.DateTimeField(null=True, blank=True)
    suspended_reason = models.CharField(max_length=255, blank=True)
    suspended_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                     on_delete=models.SET_NULL, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Student(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    admission_number = models.CharField(max_length=50)
    assessment_number = models.CharField(max_length=50, blank=True, default="")
    date_of_birth = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["school", "admission_number"],
                name="unique_admission_number_per_school",
            )
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class AcademicYear(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    name = models.CharField(max_length=20)
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.school.name} - {self.name}"


class Term(models.Model):
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE)
    name = models.CharField(max_length=20)
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.academic_year.name} - {self.name}"


class Curriculum(models.Model):
    name = models.CharField(max_length=50)
    code = models.CharField(max_length=20, unique=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class ClassLevel(models.Model):
    curriculum = models.ForeignKey(Curriculum, on_delete=models.CASCADE)
    name = models.CharField(max_length=50)
    level_number = models.PositiveIntegerField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.curriculum.name} - {self.name}"


class Stream(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    class_level = models.ForeignKey(ClassLevel, on_delete=models.CASCADE)
    name = models.CharField(max_length=50)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.class_level.name} - {self.name}"


class Enrollment(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE)
    class_level = models.ForeignKey(ClassLevel, on_delete=models.CASCADE)
    stream = models.ForeignKey(Stream, on_delete=models.SET_NULL, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.student} - {self.academic_year.name} - {self.class_level.name}"

class Subject(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, blank=True)
    definition = models.ForeignKey(
        "SubjectDefinition",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="school_subjects"
    )
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

class Performance(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE)
    term = models.ForeignKey(Term, on_delete=models.CASCADE)
    assessment_type = models.CharField(max_length=10, choices=[("opener", "Opener"), ("mid", "Mid-term"), ("end", "End-term")], default="end")
    paper_number = models.PositiveSmallIntegerField(default=1)

    marks = models.DecimalField(max_digits=5, decimal_places=2, validators=[MinValueValidator(1), MaxValueValidator(100)])
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("submitted", "Submitted"),
        ("approved", "Approved"),
        ("locked", "Locked"),
    ]
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="draft")
    entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    updated_at = models.DateTimeField(auto_now=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["student", "subject", "academic_year", "term", "assessment_type", "paper_number"], name="unique_student_subject_term_performance"),
            models.CheckConstraint(
                condition=models.Q(marks__gte=1, marks__lte=100),
                name="performance_marks_1_100",
            )
        ]

    def __str__(self):
        return f"{self.student} - {self.subject} - {self.marks}"


class TeacherProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="teacher_profile")
    school = models.ForeignKey("School", on_delete=models.CASCADE, related_name="teacher_profiles")
    staff_id = models.CharField(max_length=50, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.user.username


class SubjectDefinition(models.Model):
    curriculum = models.ForeignKey(
        "Curriculum",
        on_delete=models.PROTECT,
        related_name="subject_definitions"
    )
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=30)
    class_levels = models.ManyToManyField(
        "ClassLevel",
        blank=True,
        related_name="subject_definitions"
    )
    pathways = models.ManyToManyField(
        "CurriculumPathway", blank=True,
        related_name="subject_definitions"
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["curriculum", "code"],
                name="unique_subject_code_per_curriculum"
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.curriculum.name})"


class CurriculumPathway(models.Model):
    curriculum = models.ForeignKey(
        "Curriculum",
        on_delete=models.PROTECT,
        related_name="pathways"
    )
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=30)
    class_levels = models.ManyToManyField(
        "ClassLevel",
        blank=True,
        related_name="curriculum_pathways"
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["curriculum", "code"],
                name="unique_pathway_code_per_curriculum"
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.curriculum.name})"


class TeacherAssignment(models.Model):
    teacher = models.ForeignKey(TeacherProfile, on_delete=models.CASCADE)
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    stream = models.ForeignKey(Stream, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.teacher} - {self.subject} - {self.stream}"

class SchoolAdminProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="school_admin_profile",
    )
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="school_admins",
    )
    is_deputy = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.school.name}"





class MarkAuditLog(models.Model):
    performance = models.ForeignKey(
        Performance, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="audit_logs",
    )
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="mark_audit_logs",
        null=True, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    action = models.CharField(max_length=30)
    details = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.action} by {self.user} at {self.timestamp}"



class SubjectPaper(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="papers")
    paper_number = models.PositiveSmallIntegerField()
    weight = models.DecimalField(
        max_digits=5, decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )

    # Highest mark a teacher can enter for this paper. Marks become a
    # percentage of this before the paper weights apply.
    max_marks = models.DecimalField(
        max_digits=5, decimal_places=2, default=100,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["subject", "paper_number"], name="unique_paper_per_subject"
            )
        ]

    def __str__(self):
        return f"{self.subject} paper {self.paper_number} ({self.weight}%)"


class Exam(models.Model):
    STATUS_CHOICES = [("draft", "Draft"), ("published", "Published")]
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="exams")
    name = models.CharField(max_length=200)
    term = models.ForeignKey(Term, on_delete=models.CASCADE, related_name="exams")
    assessment_type = models.CharField(
        max_length=10,
        choices=[("opener", "Opener"), ("mid", "Mid-term"), ("end", "End-term")],
        default="end",
    )
    class_level = models.ForeignKey(ClassLevel, on_delete=models.PROTECT, related_name="exams")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="draft")
    published_at = models.DateTimeField(null=True, blank=True)
    framework_key = models.CharField(max_length=40, null=True, blank=True)
    framework_version = models.PositiveIntegerField(null=True, blank=True)
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["term", "assessment_type", "class_level"],
                name="unique_exam_per_term_type_level",
            )
        ]

    def __str__(self):
        return self.name


class ExamResult(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="results")
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="exam_results")
    overall_average = models.DecimalField(max_digits=5, decimal_places=2)
    stream_rank = models.PositiveIntegerField(null=True, blank=True)
    class_rank = models.PositiveIntegerField(null=True, blank=True)
    subject_scores = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["exam", "student"], name="unique_result_per_exam_student"
            )
        ]

    def __str__(self):
        return f"{self.student} - {self.exam} - {self.overall_average}"


class JoinRequest(models.Model):
    ROLES = [("teacher", "Teacher"), ("bursar", "Bursar"),
             ("secretary", "Secretary")]
    STATUSES = [("pending", "Pending"), ("approved", "Approved"),
                ("rejected", "Rejected"), ("joined", "Joined")]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name="join_requests")
    school = models.ForeignKey("School", on_delete=models.CASCADE,
                               related_name="join_requests")
    role = models.CharField(max_length=20, choices=ROLES)
    status = models.CharField(max_length=20, choices=STATUSES, default="pending")
    requested_at = models.DateTimeField(auto_now_add=True)
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name="+")
    decided_at = models.DateTimeField(null=True, blank=True)
    joined_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=["user"], name="one_open_join_request_per_user",
            condition=models.Q(status__in=["pending", "approved"]))]

    def __str__(self):
        return f"{self.user} -> {self.school} ({self.role}, {self.status})"


class InvitationCode(models.Model):
    request = models.OneToOneField(JoinRequest, on_delete=models.CASCADE,
                                   related_name="invitation")
    school = models.ForeignKey("School", on_delete=models.CASCADE,
                               related_name="invitation_codes")
    code = models.CharField(max_length=30, unique=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.code} ({self.school})"


class StaffProfile(models.Model):
    ROLES = [("bursar", "Bursar"), ("secretary", "Secretary")]
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name="staff_profile")
    school = models.ForeignKey("School", on_delete=models.CASCADE,
                               related_name="staff_profiles")
    role = models.CharField(max_length=20, choices=ROLES)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} - {self.role}"


class Notification(models.Model):
    KINDS = [("join_requested", "New Staff Request"),
             ("join_completed", "New staff member"),
             ("join_approved", "Request approved"),
             ("join_rejected", "Request rejected"),
             ("teacher_transfer_requested", "Teacher transfer requested"),
             ("teacher_transfer_approved", "Teacher transfer approved"),
             ("teacher_transfer_rejected", "Teacher transfer rejected")]
    school = models.ForeignKey("School", on_delete=models.CASCADE,
                               related_name="notifications")
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL,
                                  on_delete=models.CASCADE,
                                  related_name="notifications")
    kind = models.CharField(max_length=30, choices=KINDS)
    message = models.CharField(max_length=255)
    join_request = models.ForeignKey("JoinRequest", null=True, blank=True,
                                     on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["recipient", "read_at"])]


_OPEN_REG = ["pending_verification", "verified", "pending_approval",
             "needs_information"]


class SchoolRegistration(models.Model):
    """Public request to start a school. NOT a School: nothing real exists
    until a superadmin approves it."""
    TYPES = [("primary", "Primary"), ("junior", "Junior school"),
             ("secondary", "Secondary"), ("combined", "Combined / other")]
    STATUSES = [
        ("pending_verification", "Pending verification"),
        ("verified", "Verified"),
        ("pending_approval", "Pending approval"),
        ("needs_information", "Needs information"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ]
    OPEN = _OPEN_REG
    reference = models.CharField(max_length=20, unique=True)
    school_name = models.CharField(max_length=200)
    proposed_school_code = models.CharField(max_length=50)
    school_type = models.CharField(max_length=30, choices=TYPES)
    school_phone = models.CharField(max_length=30)
    school_email = models.EmailField(blank=True)
    county = models.CharField(max_length=100)
    sub_county = models.CharField(max_length=100, blank=True)
    address = models.CharField(max_length=200, blank=True)
    administrator_name = models.CharField(max_length=200)
    administrator_username = models.CharField(max_length=150)
    administrator_email = models.EmailField(blank=True)
    administrator_phone = models.CharField(max_length=30)
    password_hash = models.CharField(max_length=255)
    status = models.CharField(max_length=30, choices=STATUSES,
                              default="pending_verification")
    verification_status = models.CharField(
        max_length=20, default="unverified",
        choices=[("unverified", "Unverified"), ("verified", "Verified")])
    otp_hash = models.CharField(max_length=255, blank=True)
    otp_expires_at = models.DateTimeField(null=True, blank=True)
    otp_attempts = models.PositiveSmallIntegerField(default=0)
    otp_send_count = models.PositiveSmallIntegerField(default=0)
    otp_sent_at = models.DateTimeField(null=True, blank=True)
    authorization_confirmed_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+")
    rejection_reason = models.TextField(blank=True)
    info_request_message = models.TextField(blank=True)
    info_response_message = models.TextField(blank=True)
    info_response = models.TextField(blank=True)
    info_responded_at = models.DateTimeField(null=True, blank=True)
    internal_notes = models.TextField(blank=True)  # superadmin only
    school = models.OneToOneField(
        School, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="registration")

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["proposed_school_code"],
                condition=models.Q(status__in=_OPEN_REG),
                name="unique_open_registration_school_code"),
            models.UniqueConstraint(
                Lower("administrator_username"),
                condition=models.Q(status__in=_OPEN_REG),
                name="unique_open_registration_username"),
        ]

    def __str__(self):
        return f"{self.reference} {self.school_name}"


class FeeStructure(models.Model):
    school = models.ForeignKey("School", on_delete=models.CASCADE,
                               related_name="fee_structures")
    academic_year = models.ForeignKey("AcademicYear", on_delete=models.PROTECT,
                                      related_name="fee_structures")
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2,
                                 validators=[MinValueValidator(0)])
    due_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(
            fields=["school", "academic_year", "name"],
            name="unique_fee_structure_per_year",
        )]

    def __str__(self):
        return f"{self.name} - {self.academic_year}"


class StudentFee(models.Model):
    STATUS_CHOICES = [("pending", "Pending"), ("partial", "Partial"),
                      ("paid", "Paid"), ("waived", "Waived")]
    student = models.ForeignKey("Student", on_delete=models.CASCADE,
                                related_name="fees")
    fee_structure = models.ForeignKey("FeeStructure", on_delete=models.PROTECT,
                                      related_name="student_fees")
    amount_due = models.DecimalField(max_digits=12, decimal_places=2,
                                     validators=[MinValueValidator(0)])
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2,
                                      default=0, validators=[MinValueValidator(0)])
    status = models.CharField(max_length=10, choices=STATUS_CHOICES,
                              default="pending")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["student__last_name", "student__first_name"]
        constraints = [models.UniqueConstraint(
            fields=["student", "fee_structure"],
            name="unique_student_fee_structure",
        )]

    @property
    def balance(self):
        return max(self.amount_due - self.amount_paid, 0)

    def __str__(self):
        return f"{self.student} - {self.fee_structure.name}"


class FeePayment(models.Model):
    METHODS = [("cash", "Cash"), ("mpesa", "M-Pesa"),
               ("bank", "Bank"), ("other", "Other")]
    student_fee = models.ForeignKey("StudentFee", on_delete=models.PROTECT,
                                    related_name="payments")
    amount = models.DecimalField(max_digits=12, decimal_places=2,
                                 validators=[MinValueValidator(0.01)])
    method = models.CharField(max_length=10, choices=METHODS, default="cash")
    reference = models.CharField(max_length=80, blank=True)
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL,
                                     on_delete=models.SET_NULL, null=True,
                                     related_name="received_fee_payments")
    paid_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-paid_at"]

    def __str__(self):
        return f"{self.student_fee.student} - {self.amount}"


class GuardianProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name="guardian_profile")
    school = models.ForeignKey("School", on_delete=models.CASCADE,
                               related_name="guardian_profiles")
    phone = models.CharField(max_length=30, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.user.username


class StudentGuardian(models.Model):
    student = models.ForeignKey("Student", on_delete=models.CASCADE,
                                related_name="guardians")
    guardian = models.ForeignKey("GuardianProfile", on_delete=models.CASCADE,
                                 related_name="student_links")
    relationship = models.CharField(max_length=40, blank=True)
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=["student", "guardian"], name="unique_student_guardian")]

    def __str__(self):
        return f"{self.guardian} - {self.student}"


class AttendanceRecord(models.Model):
    STATUSES = [("present", "Present"), ("absent", "Absent"), ("late", "Late"), ("excused", "Excused")]
    student = models.ForeignKey("Student", on_delete=models.CASCADE, related_name="attendance_records")
    date = models.DateField()
    status = models.CharField(max_length=10, choices=STATUSES, default="present")
    notes = models.CharField(max_length=255, blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="recorded_attendance")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["student", "date"], name="unique_student_attendance_date")]
        ordering = ["-date", "student__last_name"]


class StudentIntervention(models.Model):
    REASONS = [("academic_decline", "Academic decline"), ("absence", "Repeated absence"), ("subject_weakness", "Subject weakness"), ("fees", "Fee-related concern"), ("welfare", "Behaviour or welfare concern"), ("other", "Other")]
    OUTCOMES = [("open", "Open"), ("monitoring", "Monitoring"), ("improved", "Improved"), ("closed", "Closed")]
    student = models.ForeignKey("Student", on_delete=models.CASCADE, related_name="interventions")
    reason = models.CharField(max_length=30, choices=REASONS)
    notes = models.TextField()
    action_plan = models.TextField(blank=True)
    follow_up_date = models.DateField(null=True, blank=True)
    outcome = models.CharField(max_length=15, choices=OUTCOMES, default="open")
    outcome_notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="created_interventions")
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

class TeacherTransferRequest(models.Model):
    STATUSES = [("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected")]
    teacher = models.ForeignKey("TeacherProfile", on_delete=models.PROTECT, related_name="transfer_requests")
    source_school = models.ForeignKey("School", on_delete=models.PROTECT, related_name="outgoing_teacher_transfers")
    target_school = models.ForeignKey("School", on_delete=models.PROTECT, related_name="incoming_teacher_transfers")
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="requested_teacher_transfers")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="approved_teacher_transfers")
    status = models.CharField(max_length=12, choices=STATUSES, default="pending")
    reason = models.TextField(blank=True)
    decision_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["teacher", "target_school"], condition=models.Q(status="pending"), name="unique_pending_teacher_transfer")]


class SuperadminSecurity(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="superadmin_security")
    totp_secret = models.CharField(max_length=64, blank=True)
    mfa_enabled = models.BooleanField(default=False)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    recovery_code_hashes = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"MFA security for {self.user.username}"


class ReportRemark(models.Model):
    """Teacher-approved remark printed on a report card. Drafts never live here."""
    FIELDS = [("class_teacher", "Class teacher"), ("principal", "Principal")]
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="report_remarks")
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="report_remarks")
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="report_remarks")
    field = models.CharField(max_length=20, choices=FIELDS)
    text = models.CharField(max_length=400)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["exam", "student", "field"],
                name="unique_report_remark_per_exam_student_field",
            )
        ]

    def __str__(self):
        return f"{self.student} - {self.exam} - {self.field}"


class ReportComment(models.Model):
    """Comment workflow row (draft or approved) used by marian_reports.
    The text that is printed lives in ReportRemark, written only on approval."""
    STATUSES = [("draft", "Draft"), ("approved", "Approved")]
    SOURCES = [("teacher", "Teacher"), ("ai", "AI-drafted")]
    id = models.CharField(primary_key=True, max_length=32)
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="report_comments")
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="report_comments")
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="report_comments")
    class_name = models.CharField(max_length=50)
    field = models.CharField(max_length=20, choices=ReportRemark.FIELDS)
    text = models.CharField(max_length=400)
    status = models.CharField(max_length=10, choices=STATUSES)
    source = models.CharField(max_length=10, choices=SOURCES)
    edited = models.BooleanField(default=False)
    approved_by = models.CharField(max_length=64, blank=True)
    created_by = models.CharField(max_length=64, blank=True)
    at = models.FloatField()

    class Meta:
        indexes = [models.Index(fields=["school", "exam"], name="reportcomment_school_exam_idx")]

    def __str__(self):
        return f"{self.student} - {self.field} - {self.status}"


class ReportSettings(models.Model):
    """Per-school report settings: grading scheme and section toggles."""
    school = models.OneToOneField(School, on_delete=models.CASCADE, related_name="report_settings")
    grading = models.JSONField(null=True, blank=True)
    sections = models.JSONField(default=dict, blank=True)
    options = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Report settings - {self.school}"


class ReportAuditEntry(models.Model):
    """Append-only audit trail for the report module. No marks or names."""
    id = models.CharField(primary_key=True, max_length=32)
    at = models.FloatField()
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="report_audit_entries")
    user_id = models.CharField(max_length=64)
    role = models.CharField(max_length=20)
    action = models.CharField(max_length=60)
    target = models.CharField(max_length=100, blank=True)
    detail = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [models.Index(fields=["school", "-at"], name="reportaudit_school_at_idx")]

    def __str__(self):
        return f"{self.action} - {self.school}"


class FrameworkVersion(models.Model):
    """One saved set of grading rules. Never edited: a change makes a new version.
    Rules are set by the school, not official KNEC rules."""
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="framework_versions")
    framework_key = models.CharField(max_length=40)
    version = models.PositiveIntegerField()
    curriculum = models.ForeignKey(Curriculum, on_delete=models.PROTECT, related_name="framework_versions")
    min_level = models.PositiveIntegerField()
    max_level = models.PositiveIntegerField()
    source = models.CharField(max_length=30, default="school")
    rules = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["school", "framework_key", "version"],
                name="unique_framework_version",
            ),
            models.CheckConstraint(
                condition=models.Q(min_level__lte=models.F("max_level")),
                name="framework_levels_ordered",
            ),
        ]

    def covers(self, class_level):
        return (class_level.curriculum_id == self.curriculum_id
                and self.min_level <= class_level.level_number <= self.max_level)

    def __str__(self):
        return f"{self.framework_key} v{self.version} - {self.school}"


class FrameworkSetting(models.Model):
    """School default (no class level) or a class-level override, optionally for one year."""
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="framework_settings")
    class_level = models.ForeignKey(
        ClassLevel, on_delete=models.CASCADE, null=True, blank=True, related_name="+",
    )
    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.CASCADE, null=True, blank=True, related_name="+",
    )
    framework_version = models.ForeignKey(
        FrameworkVersion, on_delete=models.PROTECT, related_name="settings",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["school", "class_level", "academic_year"],
                condition=models.Q(class_level__isnull=False, academic_year__isnull=False),
                name="fs_unique_level_year",
            ),
            models.UniqueConstraint(
                fields=["school", "class_level"],
                condition=models.Q(class_level__isnull=False, academic_year__isnull=True),
                name="fs_unique_level",
            ),
            models.UniqueConstraint(
                fields=["school", "academic_year"],
                condition=models.Q(class_level__isnull=True, academic_year__isnull=False),
                name="fs_unique_year",
            ),
            models.UniqueConstraint(
                fields=["school"],
                condition=models.Q(class_level__isnull=True, academic_year__isnull=True),
                name="fs_unique_default",
            ),
        ]


class FrameworkChangeLog(models.Model):
    """Append-only record of framework changes. No marks or names."""
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="framework_changes")
    class_level = models.ForeignKey(
        ClassLevel, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    from_version = models.ForeignKey(
        FrameworkVersion, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    to_version = models.ForeignKey(
        FrameworkVersion, on_delete=models.PROTECT, related_name="+",
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    results_existed = models.BooleanField(default=False)
    note = models.CharField(max_length=200, blank=True)
    at = models.DateTimeField(auto_now_add=True)


class LevelScale(models.Model):
    """A school's own list of performance levels (for example Grades 1 to 6).
    Versioned: a change makes a new row. Set by the school, not official KNEC wording.
    levels is a list of {"key", "label", "description"} in display order."""
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="level_scales")
    curriculum = models.ForeignKey(Curriculum, on_delete=models.PROTECT, related_name="level_scales")
    min_level = models.PositiveIntegerField()
    max_level = models.PositiveIntegerField()
    version = models.PositiveIntegerField()
    source = models.CharField(max_length=30, default="school")
    levels = models.JSONField(default=list)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["school", "curriculum", "version"], name="unique_level_scale_version"),
            models.CheckConstraint(
                condition=models.Q(min_level__lte=models.F("max_level")),
                name="level_scale_levels_ordered"),
        ]

    def covers(self, class_level):
        return (class_level.curriculum_id == self.curriculum_id
                and self.min_level <= class_level.level_number <= self.max_level)

    def keys(self):
        return [x["key"] for x in self.levels]

    def __str__(self):
        return f"Level scale v{self.version} - {self.school}"


class LevelResult(models.Model):
    """A level-based assessment result with no marks, percentage or letter grade.
    Same four statuses as Performance."""
    STATUS_CHOICES = [
        ("draft", "Draft"), ("submitted", "Submitted"),
        ("approved", "Approved"), ("locked", "Locked"),
    ]
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="level_results")
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="level_results")
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name="+")
    term = models.ForeignKey(Term, on_delete=models.CASCADE, related_name="+")
    assessment_type = models.CharField(
        max_length=10,
        choices=[("opener", "Opener"), ("mid", "Mid-term"), ("end", "End-term")],
        default="end",
    )
    scale = models.ForeignKey(LevelScale, on_delete=models.PROTECT, related_name="results")
    level_key = models.CharField(max_length=40)
    comment = models.CharField(max_length=300, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="draft")
    entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["student", "subject", "academic_year", "term", "assessment_type"],
                name="unique_level_result"),
        ]

    def __str__(self):
        return f"{self.student} - {self.subject} - {self.level_key}"




class ClassTeacher(models.Model):
    """The class teacher of one stream for one academic year."""
    school = models.ForeignKey("School", on_delete=models.CASCADE, related_name="class_teachers")
    stream = models.ForeignKey("Stream", on_delete=models.CASCADE, related_name="class_teachers")
    academic_year = models.ForeignKey("AcademicYear", on_delete=models.CASCADE, related_name="class_teachers")
    teacher = models.ForeignKey("TeacherProfile", on_delete=models.CASCADE, related_name="class_teacher_of")
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["stream", "academic_year"], name="ct_unique_stream_year"),
        ]


class NationalRecord(models.Model):
    """What a learner received in a national assessment, typed in by the school
    from the official result. Never calculated here and never mixed into school
    exam marks, grades or ranks. A blank subject means the overall result."""
    EXAM_CHOICES = [("kpsea", "KPSEA"), ("kjsea", "KJSEA"), ("kcse", "KCSE")]
    school = models.ForeignKey("School", on_delete=models.CASCADE, related_name="national_records")
    student = models.ForeignKey("Student", on_delete=models.CASCADE, related_name="national_records")
    exam_type = models.CharField(max_length=10, choices=EXAM_CHOICES)
    year = models.PositiveIntegerField()
    subject_name = models.CharField(max_length=80, blank=True)
    result = models.CharField(max_length=40)
    note = models.CharField(max_length=200, blank=True)
    entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["student", "exam_type", "year", "subject_name"], name="nr_unique_learner_exam_year_subject"),
        ]
