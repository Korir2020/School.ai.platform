from django.conf import settings
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator


class School(models.Model):
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50, unique=True)
    location = models.CharField(max_length=200, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Student(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    admission_number = models.CharField(max_length=50)
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
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="mark_audit_logs")
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
