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

from api import setup_views
from api import profile_views
from api import resend_views

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
from api.auth_cookie import CookieLoginView, CookieRefreshView
from api.password_recovery import password_reset_request, password_reset_confirm

urlpatterns += [
    path('api/auth/login/', CookieLoginView.as_view()),
    path('api/auth/refresh/', CookieRefreshView.as_view()),
    path('api/auth/me/', me),
    path('api/auth/logout/', logout),
    path('api/auth/change-password/', change_password),
    path('api/auth/password-reset/', password_reset_request),
    path('api/auth/password-reset/confirm/', password_reset_confirm),
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

from api.admin_accounts import admin_account_list, admin_reset_password, admin_status

urlpatterns += [
    path('api/admin-accounts/', admin_account_list),
    path('api/admin-accounts/<int:pk>/reset-password/', admin_reset_password),
    path('api/admin-accounts/<int:pk>/status/', admin_status),
]

from api.superadmin_safety import superadmin_list, superadmin_status
urlpatterns += [
    path('api/superadmin-accounts/', superadmin_list),
    path('api/superadmin-accounts/<int:pk>/status/', superadmin_status),
]
from api.mfa import mfa_setup, mfa_confirm, mfa_disable
urlpatterns += [
    path('api/auth/mfa/setup/', mfa_setup),
    path('api/auth/mfa/confirm/', mfa_confirm),
    path('api/auth/mfa/disable/', mfa_disable),
]

from api.search import search

urlpatterns += [
    path('api/search/', search),
]

from api.notifications import notifications
from api.notify_read import (
    notification_read, notification_read_all)

urlpatterns += [
    path('api/notifications/', notifications),
    path('api/notifications/read-all/', notification_read_all),
    path('api/notifications/<int:pk>/read/', notification_read),
]

from api.join_public import join_register
from api.join_admin import (
    join_request_list, join_request_approve, join_request_reject)
from api.join_complete import join_my_request, join_complete

urlpatterns += [
    path('api/join/register/', join_register),
    path('api/join/my-request/', join_my_request),
    path('api/join/complete/', join_complete),
    path('api/join-requests/', join_request_list),
    path('api/join-requests/<int:pk>/approve/', join_request_approve),
    path('api/join-requests/<int:pk>/reject/', join_request_reject),
]

from api.school_registration import school_register, school_register_status, school_register_verify
from api.registration_admin import registration_admin_list, registration_admin_action
from api.teacher_transfers import transfer_collection, transfer_action, transfer_targets
urlpatterns += [
    path('api/school-registration/', school_register),
    path('api/school-registration/status/', school_register_status),
    path('api/school-registration/verify/', school_register_verify),
    path('api/school-registration/resend/', resend_views.school_register_resend),
    path('api/admin/school-registrations/', registration_admin_list),
    path('api/admin/school-registrations/<int:pk>/action/', registration_admin_action),
    path('api/setup/', setup_views.setup_status),
    path('api/setup/complete/', setup_views.setup_complete),
    path('api/school/profile/', profile_views.school_profile),
    path('api/teacher-transfers/', transfer_collection),
    path('api/teacher-transfers/targets/', transfer_targets),
    path('api/teacher-transfers/<int:pk>/action/', transfer_action),
]

from api.fees import (
    fee_summary, fee_structures, fee_invoices, fee_payment,
    fee_payments, fee_waive, fee_report,
)
urlpatterns += [
    path('api/fees/summary/', fee_summary),
    path('api/fees/structures/', fee_structures),
    path('api/fees/invoices/', fee_invoices),
    path('api/fees/payments/', fee_payment),
    path('api/fees/payment-history/', fee_payments),
    path('api/fees/invoices/<int:pk>/waive/', fee_waive),
    path('api/fees/report/', fee_report),
]

from api.parent_portal import parent_accounts, parent_children, parent_fees
from api.documents import bulk_report_cards, fee_receipts
from api.branding import school_branding
from api.academic_reports import advanced_report
from api.student_center import student_center
from api.attendance import attendance_collection, interventions
from api.student_import import student_import
urlpatterns += [
    path('api/parents/', parent_accounts),
    path('api/parent/children/', parent_children),
    path('api/parent/children/<int:student_id>/fees/', parent_fees),
    path('api/documents/report-cards/', bulk_report_cards),
    path('api/documents/fee-receipts/', fee_receipts),
    path('api/school/branding/', school_branding),
    path('api/analytics/advanced/<int:term_id>/', advanced_report),
    path('api/students/<int:pk>/center/', student_center),
    path('api/attendance/', attendance_collection),
    path('api/students/<int:student_id>/interventions/', interventions),
    path('api/students/import/', student_import),
]

from django.conf import settings
from django.conf.urls.static import static
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

from api.school_suspension import school_suspension
urlpatterns += [
    path('api/schools/<int:pk>/suspension/', school_suspension),
]
