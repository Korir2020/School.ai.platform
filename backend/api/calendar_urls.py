from django.urls import path

from api import calendar_views as v

urlpatterns = [
    path("events/", v.calendar_events),
    path("events/<int:pk>/", v.calendar_event_detail),
]
