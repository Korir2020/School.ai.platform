from django.urls import path

from api import framework_views as v

urlpatterns = [
    path("", v.framework_overview),
    path("version/", v.framework_version),
    path("assign/", v.framework_assign),
]
