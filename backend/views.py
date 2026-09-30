from rest_framework.response import Response
from rest_framework.decorators import api_view
from schools.models import (
    School,
    Student,
    AcademicYear,
    Term,
    Curriculum,
    ClassLevel,
    Stream,
    Enrollment,
)
from .serializers import (
    SchoolSerializer,
    StudentSerializer,
    AcademicYearSerializer,
    TermSerializer,
    CurriculumSerializer,
    ClassLevelSerializer,
    StreamSerializer,
    EnrollmentSerializer,
)


@api_view(['GET'])
def school_list(request):
    schools = School.objects.all()
    serializer = SchoolSerializer(schools, many=True)
    return Response(serializer.data)


@api_view(['GET'])
def student_list(request):
    students = Student.objects.all()
    serializer = StudentSerializer(students, many=True)
    return Response(serializer.data)


@api_view(['GET'])
def academic_year_list(request):
    academic_years = AcademicYear.objects.all()
    serializer = AcademicYearSerializer(academic_years, many=True)
    return Response(serializer.data)


@api_view(['GET'])
def term_list(request):
    terms = Term.objects.all()
    serializer = TermSerializer(terms, many=True)
    return Response(serializer.data)


@api_view(['GET'])
def curriculum_list(request):
    curriculums = Curriculum.objects.all()
    serializer = CurriculumSerializer(curriculums, many=True)
    return Response(serializer.data)


@api_view(['GET'])
def class_level_list(request):
    class_levels = ClassLevel.objects.all()
    serializer = ClassLevelSerializer(class_levels, many=True)
    return Response(serializer.data)


@api_view(['GET'])
def stream_list(request):
    streams = Stream.objects.all()
    serializer = StreamSerializer(streams, many=True)
    return Response(serializer.data)

@api_view(['GET'])
def enrollment_list(request):
    enrollments = Enrollment.objects.all()
    serializer = EnrollmentSerializer(enrollments, many=True)
    return Response(serializer.data)