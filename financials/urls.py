from django.urls import path
from . import views

app_name = "financials"

urlpatterns = [
    path("", views.index, name="index"),
]
