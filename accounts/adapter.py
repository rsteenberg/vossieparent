from allauth.account.adapter import DefaultAccountAdapter
from django.conf import settings


class DevAccountAdapter(DefaultAccountAdapter):
    def is_email_verified(self, request, email):
        site = getattr(settings, "SITE_URL", "")
        if site.startswith("http://localhost:8000"):
            return True
        return super().is_email_verified(request, email)
