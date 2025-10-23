from django.urls import path
from . import views

app_name = "accounts"

urlpatterns = [
    path("preferences/", views.preferences, name="preferences"),
    path("change-email/", views.change_email, name="change_email"),
    path("confirm-old/", views.confirm_old, name="confirm_old"),
    path("confirm-new/", views.confirm_new, name="confirm_new"),
]
