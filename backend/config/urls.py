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


from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from api.auth_views import me

urlpatterns += [
    path('api/auth/login/', TokenObtainPairView.as_view()),
    path('api/auth/refresh/', TokenRefreshView.as_view()),
    path('api/auth/me/', me),
]

from api.workflow import performance_action

urlpatterns += [
    path('api/performance/<int:pk>/<str:action>/', performance_action),
]

from api.report_cards import report_card

urlpatterns += [
    path('api/report-card/<int:student_id>/<int:term_id>/', report_card),
]

from api.workflow import performance_edit

urlpatterns += [
    path('api/performance/<int:pk>/', performance_edit),
]

from api.audit import audit_log_list

urlpatterns += [
    path('api/audit-logs/', audit_log_list),
]

from api.analytics import term_summary

urlpatterns += [
    path('api/analytics/term-summary/<int:term_id>/', term_summary),
]
