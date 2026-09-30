from rest_framework.response import Response
from rest_framework.decorators import api_view

from schools.models import School, Student, AcademicYear, Term, Curriculum, ClassLevel, Stream, Enrollment, Subject, Performance
from .serializers import SchoolSerializer, StudentSerializer, AcademicYearSerializer, TermSerializer, CurriculumSerializer, ClassLevelSerializer, StreamSerializer, EnrollmentSerializer, SubjectSerializer, PerformanceSerializer


@api_view(['GET'])
def school_list(request):
    serializer = SchoolSerializer(School.objects.all(), many=True)
    return Response(serializer.data)


@api_view(['GET'])
def student_list(request):
    serializer = StudentSerializer(Student.objects.all(), many=True)
    return Response(serializer.data)


@api_view(['GET'])
def academic_year_list(request):
    serializer = AcademicYearSerializer(AcademicYear.objects.all(), many=True)
    return Response(serializer.data)


@api_view(['GET'])
def term_list(request):
    serializer = TermSerializer(Term.objects.all(), many=True)
    return Response(serializer.data)


@api_view(['GET'])
def curriculum_list(request):
    serializer = CurriculumSerializer(Curriculum.objects.all(), many=True)
    return Response(serializer.data)


@api_view(['GET'])
def class_level_list(request):
    serializer = ClassLevelSerializer(ClassLevel.objects.all(), many=True)
    return Response(serializer.data)


@api_view(['GET'])
def stream_list(request):
    serializer = StreamSerializer(Stream.objects.all(), many=True)
    return Response(serializer.data)


@api_view(['GET'])
def enrollment_list(request):
    serializer = EnrollmentSerializer, SubjectSerializer, PerformanceSerializer(Enrollment.objects.all(), many=True)
    return Response(serializer.data)

@api_view(['GET'])
def subject_list(request):
    if not request.user.is_authenticated:
        return Response({"detail": "Authentication required."}, status=401)

    if request.user.is_superuser:
        subjects = Subject.objects.all()
    else:
        from schools.models import TeacherProfile
        school_id = TeacherProfile.objects.filter(
            user=request.user
        ).values_list("school_id", flat=True).first()

        if school_id is None:
            return Response({"detail": "School access not assigned."}, status=403)

        subjects = Subject.objects.filter(school_id=school_id)

    serializer = SubjectSerializer(subjects, many=True)
    return Response(serializer.data)
@api_view(['GET', 'POST'])
def performance_list(request):
    if request.method == 'GET':
        serializer = PerformanceSerializer(Performance.objects.all(), many=True)
        return Response(serializer.data)

    serializer = PerformanceSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=201)
    return Response(serializer.errors, status=400)
