from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.contrib import messages
from .models import ParentStudentLink, Student
from crm.service import get_contact_by_id, validate_parent
from django.conf import settings
from .permissions import parent_can_view_student
from .fabric import fetch_contact_by_id as fabric_contact_by_id


@login_required
def list_students(request):
    links = (
        ParentStudentLink.objects.select_related("student")
        .filter(user=request.user, active=True)
    )
    return render(
        request,
        "students/list.html",
        {
            "links": links,
            "active_nav": "students",
        },
    )

@login_required
def switch_student(request):
    sid = request.GET.get("student_id")
    if not sid:
        messages.error(request, "No student ID provided.")
        return redirect("students:list")
    
    if not parent_can_view_student(request.user, sid):
        messages.error(request, "Unable to switch to that student. Please ensure they are linked to your profile.")
        return redirect("students:list")
        
    request.session["active_student_id"] = int(sid)
    
    # Auto-redirect back to where they came from if 'next' is set
    nxt = request.GET.get("next")
    if nxt:
        return redirect(nxt)
        
    messages.success(request, f"Switched active student.")
    return redirect("home")


@login_required
def profile(request):
    sid = request.session.get("active_student_id")
    if not sid:
        return redirect("students:list")
    if not parent_can_view_student(request.user, sid):
        return HttpResponseBadRequest("invalid student")
    st = Student.objects.filter(id=sid).first()
    if not st:
        return redirect("students:list")
    contact = None
    # Prefer Fabric if configured
    if "fabric" in settings.DATABASES and st.external_student_id:
        contact = fabric_contact_by_id(st.external_student_id)
    # Fallback to Dynamics contact fetch
    if not contact and st.external_student_id:
        contact = get_contact_by_id(st.external_student_id)
    return render(
        request,
        "students/profile.html",
        {
            "student": st,
            "contact": contact,
            "active_nav": "students",
        },
    )


@login_required
def refresh_links(request):
    # Force revalidation of parent↔student links using Fabric/Dynamics
    from crm.service import validate_parent

    try:
        validate_parent(request.user)
    except Exception:
        pass
    nxt = request.GET.get("next") or reverse("students:list")
    return redirect(nxt)


@login_required
def auto_select_student(request):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    try:
        validate_parent(request.user)
    except Exception:
        pass
    sid = request.session.get("active_student_id")
    student = None
    if sid:
        student = Student.objects.filter(id=sid).first()
        if not student:
            request.session.pop("active_student_id", None)
    if not student:
        link = (
            ParentStudentLink.objects.select_related("student")
            .filter(user=request.user, active=True)
            .order_by(
                "-last_verified_at",
                "student__first_name",
                "student__last_name",
                "student__id",
            )
            .first()
        )
        if link and link.student:
            student = link.student
            request.session["active_student_id"] = student.id
    if not student:
        return JsonResponse({"ok": False})
    name = f"{student.first_name} {student.last_name}".strip()
    if not name:
        name = f"ID {student.id}"
    label = f"{name} (ID {student.id})"
    return JsonResponse(
        {"ok": True, "student_id": student.id, "student_label": label}
    )
