from django.urls import path
from . import views

app_name = "academics"

urlpatterns = [
    path("", views.index, name="index"),
    path("transcript/", views.transcript, name="transcript"),
    path("atrisk/", views.atrisk, name="atrisk"),
]
