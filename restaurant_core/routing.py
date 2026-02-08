from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    #re_path(r'ws/order_updates/(?P<room_name>[\w\-_]+)/$', consumers.OrderConsumer.as_asgi()),
    re_path(r'ws/order/(?P<role>\w+)/(?P<user_id>[^/]+)/$', consumers.OrderConsumer.as_asgi()),
]