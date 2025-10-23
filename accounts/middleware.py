from django.utils import timezone
from django.conf import settings
from crm.service import validate_parent

class IdentityLeaseMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user and user.is_authenticated and getattr(user, "is_parent", False):
            ttl = getattr(settings, "IDENTITY_LEASE_TTL_SECONDS", 3600)
            if not user.last_validated_at or (timezone.now() - user.last_validated_at).total_seconds() > ttl:
                validate_parent(user)
        return self.get_response(request)
