"""Routes for the report API. They exist only when marian_reports is installed.

When it is installed, production (not DJANGO_DEBUG, not a test run) refuses
to start without MARIAN_REPORT_SECRET and MARIAN_VERIFY_BASE.
"""
import os
import sys

from django.core.exceptions import ImproperlyConfigured
from django.urls import path

report_urlpatterns = []

try:
    import marian_reports  # noqa: F401
except ImportError:
    marian_reports = None

if marian_reports is not None:
    testing = len(sys.argv) > 1 and sys.argv[1] == "test"
    if os.environ.get("DJANGO_DEBUG") != "True" and not testing:
        if len(os.environ.get("MARIAN_REPORT_SECRET", "")) < 32:
            raise ImproperlyConfigured(
                "Set MARIAN_REPORT_SECRET (32+ characters) in production.")
        if not os.environ.get("MARIAN_VERIFY_BASE"):
            raise ImproperlyConfigured(
                "Set MARIAN_VERIFY_BASE (public base URL) in production.")
    from api import report_views as v
    P = "api/report-module/"
    report_urlpatterns = [
        path(P + "meta/", v.report_meta),
        path(P + "selection/", v.report_selection),
        path(P + "student/<int:student_id>/pdf/", v.report_student_pdf),
        path(P + "analytics/", v.report_analytics),
        path(P + "rankings/", v.report_rankings),
        path(P + "support-list/", v.report_support_list),
        path(P + "export/<str:fmt>/", v.report_export),
        path(P + "verify/<path:report_no>/", v.report_verify),
        path(P + "comments/", v.report_comments_list),
        path(P + "comments/draft/", v.report_comment_draft),
        path(P + "comments/<str:cid>/", v.report_comment_edit),
        path(P + "comments/<str:cid>/approve/", v.report_comment_approve),
        path(P + "comments/<str:cid>/reject/", v.report_comment_reject),
        path(P + "grading-config/", v.report_grading_config),
        path(P + "section-config/", v.report_section_config),
        path(P + "options/", v.report_options),
        path(P + "audit/", v.report_audit),
    ]
