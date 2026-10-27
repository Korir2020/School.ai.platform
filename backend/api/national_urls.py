from django.urls import path

from api import national_views as v

urlpatterns = [
    path("class-teachers/", v.class_teachers),
]
