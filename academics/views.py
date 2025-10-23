from django.contrib.auth.decorators import login_required
from django.shortcuts import render

@login_required
def index(request):
    sid = request.session.get("active_student_id")
    ctx = {"active_nav": "academics", "active_student_id": sid}
    return render(request, "academics/index.html", ctx)
