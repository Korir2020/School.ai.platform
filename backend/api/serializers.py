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
