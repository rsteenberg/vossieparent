from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect, render
from .models import ParentStudentLink
from crm.service import get_contact_by_id
from django.conf import settings
from .permissions import parent_can_view_student

@login_required
def list_students(request):
    links = (
        ParentStudentLink.objects.select_related("student")
        .filter(user=request.user, active=True)
    )
    # Optional: fetch a specific contact details (for demo / debug) if requested or fixed id
    demo_contact_status = {}
    if not settings.DYNAMICS_ORG_URL:
        contact_detail = None
        demo_contact_status = {
            "status": "disabled",
            "message": "Dynamics is not configured (DYNAMICS_ORG_URL is empty).",
        }
    else:
        contact_detail = get_contact_by_id("16b7f729-473c-ee11-bdf4-000d3adf7716")
        if not contact_detail:
            demo_contact_status = {
                "status": "unavailable",
                "message": "Contact could not be retrieved (permissions, ID, or network).",
            }
    return render(
        request,
        "students/list.html",
        {
            "links": links,
            "active_nav": "students",
            "demo_contact": contact_detail,
            "demo_contact_status": demo_contact_status,
        },
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
