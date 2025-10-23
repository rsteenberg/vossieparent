from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest
from django.shortcuts import render

@login_required
def index(request):
    if request.method == "POST":
        subject = request.POST.get("subject")
        body = request.POST.get("body")
        category = request.POST.get("category", "Technical")
        if not subject or not body:
            return HttpResponseBadRequest("subject and body required")
        from .models import Ticket
        from students.permissions import parent_can_view_student
        sid = request.POST.get("student_id")
        student = None
        if sid:
            if not parent_can_view_student(request.user, sid):
                return HttpResponseBadRequest("invalid student")
            from students.models import Student
            student = Student.objects.filter(id=sid).first()
        Ticket.objects.create(user=request.user, student=student, category=category, subject=subject, body=body)
        return render(request, "support/index.html", {"submitted": True, "active_nav": "support"})
    return render(request, "support/index.html", {"active_nav": "support"})
