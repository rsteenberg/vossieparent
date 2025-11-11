from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from decimal import Decimal
from students.models import Student
from students.permissions import parent_can_view_student
from crm.service import get_contact_balance


@login_required
def index(request):
    sid = request.session.get("active_student_id")
    ctx = {"active_nav": "financials", "active_student_id": sid}
    student = None
    balance = None
    balance_status = None
    if sid:
        student = Student.objects.filter(id=sid).first()
        if student and parent_can_view_student(request.user, student.id):
            ext_id = student.external_student_id
            bal = get_contact_balance(ext_id)
            if bal:
                balance = bal
                amt = bal.get("amount")
                label = bal.get("formatted") or ""
                if amt is not None:
                    if amt >= Decimal("0"):
                        balance_status = f"Current Payment Due: {label}"
                    else:
                        balance_status = f"Currently no payment due: {label}"
                else:
                    balance_status = f"Balance: {label}" if label else None
    if student:
        ctx.update({
            "student": student,
            "balance": balance,
            "balance_status": balance_status,
        })
    return render(request, "financials/index.html", ctx)
