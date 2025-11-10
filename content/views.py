from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render, get_object_or_404
from django.db.models import Exists, OuterRef
from .models import Announcement, ReadReceipt
from .services import get_notice_buckets_for_user
from students.models import ParentStudentLink
from academics.models import Enrollment

from django.views.decorators.http import require_GET


def _user_can_view_announcement(user, ann: Announcement) -> bool:
    if ann.audience == "ALL":
        return True
    if ann.audience == "PARENT":
        return ann.to_user_id == user.id or ann.to_user_id is None
    if ann.audience == "STUDENT":
        return ParentStudentLink.objects.filter(
            user=user, student_id=ann.student_id, active=True
        ).exists()
    if ann.audience == "MODULE":
        return Enrollment.objects.filter(
            student__in=ParentStudentLink.objects.filter(
                user=user, active=True
            ).values_list("student_id", flat=True),
            module_id=ann.module_id,
        ).exists()
    return False


@login_required
def documents(request):
    sid = request.session.get("active_student_id")
    ctx = {"active_student_id": sid, "active_nav": "documents"}
    return render(request, "content/documents.html", ctx)


@login_required
def announcements(request):
    buckets = get_notice_buckets_for_user(request.user, window_days=None)
    # annotate read status
    read_qs = ReadReceipt.objects.filter(
        user=request.user, announcement_id=OuterRef("pk")
    )

    def annotate(items):
        ids = [a.id for a in items]
        if not ids:
            return []
        ann_map = {
            a.id: a
            for a in Announcement.objects.filter(id__in=ids).annotate(
                is_read=Exists(read_qs)
            )
        }
        return [ann_map[i] for i in ids]

    ctx = {
        "personal": annotate(buckets["personal"]),
        "student": annotate(buckets["student"]),
        "module": annotate(buckets["module"]),
        "general": annotate(buckets["general"]),
        "active_nav": "announcements",
    }
    return render(request, "content/announcements.html", ctx)


@login_required
def announcement_detail(request, pk: int):
    ann = get_object_or_404(Announcement, pk=pk, is_active=True)
    if not _user_can_view_announcement(request.user, ann):
        return HttpResponseForbidden("Not authorized")
    ReadReceipt.objects.get_or_create(user=request.user, announcement=ann)
    return render(
        request,
        "content/announcement_detail.html",
        {"ann": ann, "active_nav": "announcements"},
    )


@require_GET
def terms(request):
    """Public Terms of Service page (no auth required)."""
    return render(request, "content/terms.html", {"active_nav": None})


@require_GET
def privacy(request):
    """Public Privacy Policy page (no auth required)."""
    return render(request, "content/privacy.html", {"active_nav": None})
