from django.urls import path
from . import views

app_name = "academics"

urlpatterns = [
    path("", views.index, name="index"),
]
