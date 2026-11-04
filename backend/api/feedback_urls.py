from django.urls import path

from api import feedback_views as v

urlpatterns = [
    path("", v.feedback),
    path("all/", v.feedback_all),
    path("summary/", v.feedback_summary),
    path("<int:pk>/", v.feedback_detail),
    path("<int:pk>/read/", v.feedback_read),
]
