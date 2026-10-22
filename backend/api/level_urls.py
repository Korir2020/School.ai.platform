from django.urls import path

from api import level_views as v

urlpatterns = [
    path("roster/", v.level_roster),
    path("save/", v.level_save),
    path("move/", v.level_move),
    path("scales/", v.level_scales),
]
