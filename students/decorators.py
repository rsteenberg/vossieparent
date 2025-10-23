from functools import wraps
from django.http import HttpResponseForbidden
from .permissions import parent_can_view_student


def require_parent_access_to_student(param: str = "student_id"):
    """
    Decorator to guard views that expose student data.
    Expects a "student_id" in URL kwargs (default) or in GET/POST.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            sid = kwargs.get(param) or request.GET.get(param) or request.POST.get(param)
            if not sid or not parent_can_view_student(request.user, sid):
                return HttpResponseForbidden("Not authorized")
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator
