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


from django.urls import path as _att_path
from api import connect_views as _att_views

urlpatterns += [_att_path("attachments/<int:pk>/", _att_views.attachment_file)]
urlpatterns += [
    _att_path("avatar/", _att_views.my_avatar),
    _att_path("posts/<int:pk>/avatar/", _att_views.post_avatar),
]
