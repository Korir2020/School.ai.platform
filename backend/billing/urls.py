from django.urls import path

from . import api

urlpatterns = [
    path("school/", api.school_billing),
    path("school/invoices/", api.school_invoice_request),
    path("school/capacity-request/", api.school_capacity_request),
    path("school/bank-transfer/", api.school_submit_bank_transfer),
    path("admin/overview/", api.admin_billing_overview),
    path("admin/schools/<int:school_id>/", api.admin_billing_school_detail),
    path("admin/schools/<int:school_id>/profile/", api.admin_profile_update),
    path("admin/pricing/", api.admin_billing_pricing),
    path("admin/invoices/", api.admin_create_invoice),
    path("admin/payments/<int:payment_id>/review/", api.admin_review_payment),
    path("admin/capacity-requests/<int:request_id>/decision/", api.admin_capacity_decision),
    path("admin/audit/", api.admin_billing_audit),
    path("callbacks/", api.payment_callback),
]
