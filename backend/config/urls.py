from api.auth_throttle import LoginView
from api.admin_create import academic_year_collection, term_collection, stream_collection, subject_collection, enrollment_collection, teacher_assignment_collection
from api.students_api import student_collection
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
    path('api/students/', student_collection),
    path('api/academic-years/', academic_year_collection),
    path('api/terms/', term_collection),
    path('api/curriculums/', curriculum_list),
    path('api/class-levels/', class_level_list),
    path('api/streams/', stream_collection),
    path('api/enrollments/', enrollment_collection),
    path('api/subjects/', subject_collection),
    path('api/performance/', performance_list),
]


from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from api.auth_views import me
from api.auth_logout import logout
from api.auth_password import change_password

urlpatterns += [
    path('api/auth/login/', LoginView.as_view()),
    path('api/auth/refresh/', TokenRefreshView.as_view()),
    path('api/auth/me/', me),
    path('api/auth/logout/', logout),
    path('api/auth/change-password/', change_password),
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

from api.papers import subject_paper_list

urlpatterns += [
    path('api/subject-papers/', subject_paper_list),
]

from api.exams import exam_list

urlpatterns += [
    path('api/exams/', exam_list),
]

from api.exam_publish import exam_publish

urlpatterns += [
    path('api/exams/<int:pk>/publish/', exam_publish),
]

from api.results import exam_results, student_exam_history

urlpatterns += [
    path('api/exams/<int:pk>/results/', exam_results),
    path('api/students/<int:student_id>/exam-history/', student_exam_history),
]

urlpatterns += [
    path('api/teacher-assignments/', teacher_assignment_collection),
]

from api.admin_edit import (
    student_detail, academic_year_detail, term_detail, stream_detail,
    subject_detail, enrollment_detail, teacher_assignment_detail,
)

urlpatterns += [
    path('api/students/<int:pk>/', student_detail),
    path('api/academic-years/<int:pk>/', academic_year_detail),
    path('api/terms/<int:pk>/', term_detail),
    path('api/streams/<int:pk>/', stream_detail),
    path('api/subjects/<int:pk>/', subject_detail),
    path('api/enrollments/<int:pk>/', enrollment_detail),
    path('api/teacher-assignments/<int:pk>/', teacher_assignment_detail),
]

from api.paper_edit import subject_paper_detail

urlpatterns += [
    path('api/subject-papers/<int:pk>/', subject_paper_detail),
]

from api.dashboard import dashboard

urlpatterns += [
    path('api/dashboard/', dashboard),
]

from api.health import health

urlpatterns += [
    path('api/health/', health),
]

from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns += [
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='docs'),
]

from api.progress_api import student_progress

urlpatterns += [
    path('api/students/<int:student_id>/progress/', student_progress),
]

from api.early_warning import early_warning

urlpatterns += [
    path('api/analytics/early-warning/', early_warning),
]

from api.teachers import teacher_collection

urlpatterns += [
    path('api/teachers/', teacher_collection),
]

from api.deputies import deputy_collection, deputy_detail

urlpatterns += [
    path('api/deputies/', deputy_collection),
    path('api/deputies/<int:pk>/', deputy_detail),
]

from api.teacher_accounts import teacher_detail, teacher_reset_password

urlpatterns += [
    path('api/teachers/<int:pk>/', teacher_detail),
    path('api/teachers/<int:pk>/reset-password/', teacher_reset_password),
]

from api.approvals_summary import approvals_summary

urlpatterns += [
    path('api/approvals/summary/', approvals_summary),
]
