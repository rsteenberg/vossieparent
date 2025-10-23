from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect, render
from .models import ParentStudentLink
from .permissions import parent_can_view_student

@login_required
def list_students(request):
    links = (
        ParentStudentLink.objects.select_related("student")
        .filter(user=request.user, active=True)
    )
    return render(
        request,
        "students/list.html",
        {"links": links, "active_nav": "students"},
    )

@login_required
def switch_student(request):
    sid = request.GET.get("student_id")
    if not sid:
        return HttpResponseBadRequest("student_id required")
    if not parent_can_view_student(request.user, sid):
        return HttpResponseBadRequest("invalid student")
    request.session["active_student_id"] = int(sid)
    return redirect("home")
