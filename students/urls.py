from django.urls import path
from . import views

app_name = "students"

urlpatterns = [
    path("students/", views.list_students, name="list"),
    path("students/switch/", views.switch_student, name="switch"),
]
