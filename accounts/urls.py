from django.urls import path
from . import views

app_name = "accounts"

urlpatterns = [
    path("preferences/", views.preferences, name="preferences"),
    path("preferences/send-progress/", views.send_progress_now, name="send_progress_now"),
    path("emails/", views.alternate_emails, name="alternate_emails"),
    path("change-email/", views.change_email, name="change_email"),
    path("confirm-old/", views.confirm_old, name="confirm_old"),
    path("confirm-new/", views.confirm_new, name="confirm_new"),
]
