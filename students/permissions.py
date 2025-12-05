import logging
from django.conf import settings
from django.utils import timezone
from .models import ParentStudentLink

logger = logging.getLogger(__name__)

def parent_can_view_student(user, student_id) -> bool:
    if not getattr(user, "is_authenticated", False) or not getattr(user, "is_parent", False):
        return False
        
    ttl = getattr(settings, "IDENTITY_LEASE_TTL_SECONDS", 3600)
    if not user.last_validated_at or (timezone.now() - user.last_validated_at).total_seconds() > ttl:
        from crm.service import validate_parent
        try:
            if not validate_parent(user):
                logger.warning(f"Permission denied: validate_parent failed for user {user.pk}")
                return False
        except Exception as e:
            logger.error(f"Permission denied: validate_parent raised exception for user {user.pk}: {e}")
            return False

    has_link = ParentStudentLink.objects.filter(user=user, student_id=student_id, active=True).exists()
    if not has_link:
        logger.warning(f"Permission denied: User {user.pk} has no active link to student {student_id}")
        
    return has_link
