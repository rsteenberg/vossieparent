from datetime import timedelta
from django.utils import timezone
from django.db.models import Q
from .models import Announcement

def _active_window_q(window_start):
    now = timezone.now()
    q = Q(is_active=True) & Q(published_at__lte=now)
    q &= Q(expires_at__isnull=True) | Q(expires_at__gt=now)
    if window_start is not None:
        q &= Q(published_at__gte=window_start)
    return q

def get_notice_buckets_for_user(user, window_days: int | None = 7):
    """
    Returns notices in four buckets for a parent user.
    If window_days is None, returns without a date window (all active).
    """
    from students.models import ParentStudentLink
    from academics.models import Enrollment

    if window_days is not None:
        window_start = timezone.now() - timedelta(days=window_days)
    else:
        window_start = None

    base_q = _active_window_q(window_start)

    student_ids = list(
        ParentStudentLink.objects.filter(user=user, active=True)
        .values_list("student_id", flat=True)
    )

    module_ids = []
    if student_ids:
        module_ids = list(
            Enrollment.objects.filter(student_id__in=student_ids)
            .values_list("module_id", flat=True)
        )

    qs = Announcement.objects.filter(base_q).order_by("-published_at")

    personal = qs.filter(audience="PARENT", to_user=user)
    student_scoped = qs.filter(audience="STUDENT", student_id__in=student_ids)
    module_scoped = qs.filter(audience="MODULE", module_id__in=module_ids)
    general = qs.filter(audience="ALL") | qs.filter(
        audience="PARENT", to_user__isnull=True
    )

    return {
        "personal": list(personal),
        "student": list(student_scoped),
        "module": list(module_scoped),
        "general": list(general),
    }
