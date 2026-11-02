from django.urls import path

from api import connect_views as v

urlpatterns = [
    path("channels/", v.channels),
    path("channels/<int:pk>/posts/", v.channel_posts),
    path("posts/<int:pk>/", v.post_detail),
    path("posts/<int:pk>/ack/", v.post_ack),
    path("posts/<int:pk>/report/", v.post_report),
    path("reports/", v.reports),
    path("reports/<int:pk>/resolve/", v.report_resolve),
    path("members/", v.members),
    path("members/<int:user_id>/mute/", v.member_mute),
]
