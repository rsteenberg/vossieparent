from django.contrib.auth.decorators import login_required
from django.shortcuts import render

@login_required
def index(request):
    sid = request.session.get("active_student_id")
    ctx = {"active_nav": "attendance", "active_student_id": sid}
    return render(request, "attendance/index.html", ctx)
