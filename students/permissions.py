from django.conf import settings
from django.utils import timezone
from .models import ParentStudentLink

def parent_can_view_student(user, student_id) -> bool:
    if not getattr(user, "is_authenticated", False) or not getattr(user, "is_parent", False):
        return False
    ttl = getattr(settings, "IDENTITY_LEASE_TTL_SECONDS", 3600)
    if not user.last_validated_at or (timezone.now() - user.last_validated_at).total_seconds() > ttl:
        from crm.service import validate_parent
        if not validate_parent(user):
            return False
    return ParentStudentLink.objects.filter(user=user, student_id=student_id, active=True).exists()
