from rest_framework import serializers
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
    class Meta:
        model = Stream
        fields = '__all__'


class EnrollmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Enrollment
        fields = '__all__'

class SubjectSerializer(serializers.ModelSerializer):
    definition_name = serializers.CharField(
        source="definition.name", read_only=True, allow_null=True
    )
    curriculum_code = serializers.CharField(
        source="definition.curriculum.code", read_only=True, allow_null=True
    )

    class Meta:
        model = Subject
        fields = (
            "id", "school", "name", "code", "is_active",
            "definition", "definition_name", "curriculum_code"
        )
class PerformanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Performance
        fields = '__all__'
        read_only_fields = ('status', 'entered_by', 'updated_at')

    def validate(self, attrs):
        term = attrs.get("term")
        year = attrs.get("academic_year")
        if term and year and term.academic_year_id != year.id:
            raise serializers.ValidationError(
                "Term does not belong to the selected academic year."
            )
        subject = attrs.get("subject")
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
        marks = attrs.get("marks")
        inst = getattr(self, "instance", None)
        subj = subject or (inst.subject if inst is not None else None)
        pno = attrs.get("paper_number", inst.paper_number if inst is not None else 1)
        if marks is not None and subj is not None:
            from schools.models import SubjectPaper
            paper = SubjectPaper.objects.filter(subject=subj, paper_number=pno).first()
            if paper is not None and marks > paper.max_marks:
                top = format(paper.max_marks.normalize(), "f")
                raise serializers.ValidationError(
                    {"marks": ["Marks cannot be above " + top + " for this paper."]}
                )
        return attrs
