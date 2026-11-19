from django.urls import path

from .views import live_stream

urlpatterns = [
    path("", live_stream, name="live-stream"),
]
