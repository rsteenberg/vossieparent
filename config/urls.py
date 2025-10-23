from django.contrib import admin
from django.urls import include, path
from accounts import views as accounts_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("django-rq/", include("django_rq.urls")),
    path("webhooks/email/", include("mailer.webhooks_urls")),
    path("accounts/", include("allauth.urls")),
    # app URLs
    path("parents/", include("accounts.urls")),
    path("", accounts_views.home, name="home"),
    # portal sections
    path("academics/", include("academics.urls")),
    path("attendance/", include("attendance.urls")),
    path("financials/", include("financials.urls")),
    path("support/", include("support.urls")),
    # content (documents, announcements) as top-level routes
    path("", include("content.urls")),
    # students list/switch
    path("", include("students.urls")),
    # unsubscribe route
    path("", include("mailer.urls")),
]
