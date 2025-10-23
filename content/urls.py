from django.urls import path
from . import views

app_name = "content"

urlpatterns = [
    path("documents/", views.documents, name="documents"),
    path("announcements/", views.announcements, name="announcements"),
    path("announcements/<int:pk>/", views.announcement_detail, name="announcement_detail"),
]
