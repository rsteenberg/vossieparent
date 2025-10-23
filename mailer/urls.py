from django.urls import path
from . import views

app_name = "mailer"

urlpatterns = [
    path("unsubscribe/", views.unsubscribe, name="unsubscribe"),
]
