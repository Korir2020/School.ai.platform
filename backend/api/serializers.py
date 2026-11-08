from rest_framework import serializers
from django.db.models.functions import Lower, Trim
from schools.models import (
    School,
    Student,
    AcademicYear,
    Term,
    Curriculum,
    ClassLevel,
    Stream,
    Enrollment, Subject, Performance,
)


class SchoolSerializer(serializers.ModelSerializer):
    class Meta:
        model = School
        fields = '__all__'


class StudentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Student
        fields = '__all__'
        read_only_fields = ['status']  # changed only via promotion / exit / re-admit


class AcademicYearSerializer(serializers.ModelSerializer):
    class Meta:
        model = AcademicYear
        fields = '__all__'


class TermSerializer(serializers.ModelSerializer):
    class Meta:
        model = Term
        fields = '__all__'


class CurriculumSerializer(serializers.ModelSerializer):
    class Meta:
        model = Curriculum
        fields = '__all__'


class ClassLevelSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClassLevel
        fields = '__all__'


class StreamSerializer(serializers.ModelSerializer):
    class_level_name = serializers.CharField(source="class_level.name", read_only=True)

    class Meta:
        model = Stream
        fields = '__all__'

    def validate(self, attrs):
        school = attrs.get("school") or getattr(self.instance, "school", None)
        name = attrs.get("name", getattr(self.instance, "name", ""))
        name = str(name or "").strip()
        if not name:
            raise serializers.ValidationError({"name": ["Enter a stream name."]})
        if school and Stream.objects.annotate(_normalized_name=Lower(Trim("name"))).filter(
            school=school, _normalized_name=name.lower(),
        ).exclude(pk=getattr(self.instance, "pk", None)).exists():
            raise serializers.ValidationError({
                "name": ["A stream with this name already exists in this school."]
            })
        attrs["name"] = name
        return attrs


class EnrollmentSerializer(serializers.ModelSerializer):
    class_level_name = serializers.CharField(source="class_level.name", read_only=True)
    class_level_number = serializers.IntegerField(source="class_level.level_number", read_only=True)
    curriculum_code = serializers.CharField(source="class_level.curriculum.code", read_only=True)
    pathway_name = serializers.CharField(source="pathway.name", read_only=True, allow_null=True)
    pathway_code = serializers.CharField(source="pathway.code", read_only=True, allow_null=True)

    class Meta:
        model = Enrollment
        fields = (
            "id", "student", "academic_year", "class_level", "pathway", "stream",
            "is_active", "created_at", "class_level_name", "class_level_number",
            "curriculum_code", "pathway_name", "pathway_code",
        )

    def validate(self, attrs):
        from api.senior_rules import is_cbc_senior, pathway_matches_class

        instance = getattr(self, "instance", None)
        class_level = attrs.get("class_level", instance.class_level if instance else None)
        pathway = attrs.get("pathway", instance.pathway if instance else None)
        if class_level is None:
            return attrs
        if is_cbc_senior(class_level):
            # Existing legacy enrollments may remain unassigned until their
            # administrator records a path; new Senior enrollments may not.
            class_changed = instance is None or (
                "class_level" in attrs and attrs["class_level"].pk != instance.class_level_id
            )
            if pathway is None and (class_changed or "pathway" in attrs):
                raise serializers.ValidationError({"pathway": ["Choose a CBC Senior pathway for this enrollment."]})
            if pathway is not None and not pathway_matches_class(pathway, class_level):
                raise serializers.ValidationError({"pathway": ["Choose an active pathway that applies to this CBC Senior grade."]})
        elif pathway is not None:
            raise serializers.ValidationError({"pathway": ["Pathways apply only to CBC Senior Grades 10–12."]})
        return attrs

class SubjectSerializer(serializers.ModelSerializer):
    definition_name = serializers.CharField(
        source="definition.name", read_only=True, allow_null=True
    )
    curriculum_code = serializers.CharField(
        source="definition.curriculum.code", read_only=True, allow_null=True
    )
    definition_class_levels = serializers.SerializerMethodField()
    definition_pathways = serializers.SerializerMethodField()

    def get_definition_class_levels(self, obj):
        if not obj.definition_id:
            return []
        return [level.pk for level in obj.definition.class_levels.all()]

    def get_definition_pathways(self, obj):
        if not obj.definition_id:
            return []
        return [{"id": pathway.pk, "code": pathway.code, "name": pathway.name}
                for pathway in obj.definition.pathways.all()]

    class Meta:
        model = Subject
        fields = (
            "id", "school", "name", "code", "is_active",
            "definition", "definition_name", "curriculum_code",
            "definition_class_levels", "definition_pathways",
        )

    def validate(self, attrs):
        school = attrs.get("school") or getattr(self.instance, "school", None)
        name = attrs.get("name", getattr(self.instance, "name", ""))
        name = str(name or "").strip()
        if not name:
            raise serializers.ValidationError({"name": ["Enter a subject name."]})
        if school and Subject.objects.annotate(_normalized_name=Lower(Trim("name"))).filter(
            school=school, _normalized_name=name.lower(),
        ).exclude(pk=getattr(self.instance, "pk", None)).exists():
            raise serializers.ValidationError({
                "name": ["A subject with this name already exists in this school."]
            })
        attrs["name"] = name
        return attrs

class PerformanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Performance
        fields = '__all__'
        read_only_fields = ('status', 'entered_by', 'updated_at')

    def validate(self, attrs):
        from schools.models import SubjectRegistration

        instance = getattr(self, "instance", None)
        term = attrs.get("term")
        year = attrs.get("academic_year")
        student = attrs.get("student", instance.student if instance is not None else None)
        subject = attrs.get("subject", instance.subject if instance is not None else None)
        year = year or (instance.academic_year if instance is not None else None)
        if term and year and term.academic_year_id != year.id:
            raise serializers.ValidationError(
                "Term does not belong to the selected academic year."
            )
        if student is not None and year is not None and subject is not None:
            from api.senior_rules import is_cbc_senior, pathway_matches_class, subject_definition_problem
            if student.school_id != year.school_id or subject.school_id != student.school_id:
                raise serializers.ValidationError(
                    "Student, subject, and academic year must belong to the same school."
                )
            enrollment = Enrollment.objects.filter(
                student=student, academic_year=year, is_active=True,
            ).select_related("class_level__curriculum", "pathway").first()
            if enrollment is None:
                raise serializers.ValidationError(
                    "The learner has no active enrollment in this academic year."
                )
            if is_cbc_senior(enrollment.class_level):
                if not pathway_matches_class(enrollment.pathway, enrollment.class_level):
                    raise serializers.ValidationError("The learner needs a valid CBC Senior pathway for this academic year.")
                problem = subject_definition_problem(subject.definition, enrollment.class_level, enrollment.pathway)
                if problem:
                    raise serializers.ValidationError(problem)
            if not SubjectRegistration.objects.filter(
                student=student, academic_year=year, subject=subject,
            ).exists():
                raise serializers.ValidationError(
                    "The learner is not registered for this subject in this academic year."
                )
        if subject:
            from schools.models import SubjectPaper
            numbers = list(
                SubjectPaper.objects.filter(subject=subject)
                .values_list("paper_number", flat=True)
            )
            if numbers and attrs.get("paper_number", 1) not in numbers:
                raise serializers.ValidationError(
                    "Paper number is not defined for this subject."
                )
        inst = getattr(self, "instance", None)
        subj = subject or (inst.subject if inst is not None else None)
        pno = attrs.get("paper_number", inst.paper_number if inst is not None else 1)
        mark_status = attrs.get(
            "mark_status", inst.mark_status if inst is not None else "scored",
        )
        marks = attrs.get("marks", inst.marks if inst is not None else None)
        if mark_status == "scored" and marks is None:
            raise serializers.ValidationError({"marks": ["A numeric mark is required for a scored entry; zero is valid."]})
        if mark_status != "scored" and marks is not None:
            raise serializers.ValidationError({"marks": ["Non-scored statuses must not include a numeric mark."]})
        if marks is not None and subj is not None:
            from schools.models import SubjectPaper
            paper = SubjectPaper.objects.filter(subject=subj, paper_number=pno).first()
            if paper is not None and marks > paper.max_marks:
                top = format(paper.max_marks.normalize(), "f")
                raise serializers.ValidationError(
                    {"marks": ["Marks cannot be above " + top + " for this paper."]}
                )
        return attrs
