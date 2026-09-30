from django.contrib import admin
from django.urls import path
from api.views import (
    performance_list,
    school_list,
    student_list,
    academic_year_list,
    term_list,
    curriculum_list,
    class_level_list,
    stream_list,
    enrollment_list, subject_list,
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/schools/', school_list),
    path('api/students/', student_list),
    path('api/academic-years/', academic_year_list),
    path('api/terms/', term_list),
    path('api/curriculums/', curriculum_list),
    path('api/class-levels/', class_level_list),
    path('api/streams/', stream_list),
    path('api/enrollments/', enrollment_list),
    path('api/subjects/', subject_list),
    path('api/performance/', performance_list),
]
