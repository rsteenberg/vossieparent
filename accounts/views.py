import secrets
from datetime import timedelta
from django.contrib.auth.decorators import login_required
from django.contrib.auth import update_session_auth_hash
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from allauth.account.models import EmailAddress
from .models import EmailPreference, EmailChangeRequest
from students.models import Student
from mailer.models import Campaign, MessageLog, EmailTemplate
from jobs.tasks import send_parent_update

def home(request):
    if request.user.is_authenticated:
        prefs_url = reverse("accounts:preferences")
        change_email_url = reverse("accounts:change_email")
        students_list_url = reverse("students:list")
        academics_url = reverse("academics:index")
        attendance_url = reverse("attendance:index")
        financials_url = reverse("financials:index")
        documents_url = reverse("content:documents")
        announcements_url = reverse("content:announcements")
        support_url = reverse("support:index")
        name = getattr(request.user, "first_name", "") or request.user.email
        sid = request.session.get("active_student_id")
        student_label = "None selected"
        if sid:
            st = Student.objects.filter(id=sid).first()
            if st:
                student_label = f"{st.first_name} {st.last_name} (ID {st.id})"
        ctx = {
            "name": name,
            "student_label": student_label,
            "students_list_url": students_list_url,
            "prefs_url": prefs_url,
            "change_email_url": change_email_url,
            "academics_url": academics_url,
            "attendance_url": attendance_url,
            "financials_url": financials_url,
            "documents_url": documents_url,
            "announcements_url": announcements_url,
            "support_url": support_url,
            "active_nav": "dashboard",
        }
        return render(request, "home.html", ctx)
    return redirect("account_login")

@login_required
def preferences(request):
    if request.method == "POST":
        opt_in = bool(request.POST.get("marketing_opt_in"))
        ep, _ = EmailPreference.objects.get_or_create(user=request.user)
        ep.marketing_opt_in = opt_in
        ep.consent_source = "preferences"
        ep.consent_timestamp = timezone.now()
        ep.save()
        return redirect("accounts:preferences")
    checked = bool(getattr(request.user, "email_pref", None) and request.user.email_pref.marketing_opt_in)
    return render(
        request,
        "accounts/preferences.html",
        {"opt_in_checked": checked, "active_nav": "preferences", "just_sent": bool(request.GET.get("sent"))},
    )

@login_required
def change_email(request):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    new_email = request.POST.get("new_email")
    if not new_email:
        return HttpResponseBadRequest("new_email required")
    token1 = secrets.token_urlsafe(32)[:64]
    token2 = secrets.token_urlsafe(32)[:64]
    ecr = EmailChangeRequest.objects.create(
        user=request.user,
        new_email=new_email,
        old_email_token=token1,
        new_email_token=token2,
        expires_at=timezone.now() + timedelta(days=1),
    )
    base = settings.SITE_URL.rstrip("/")
    old_link = f"{base}{reverse('accounts:confirm_old')}?t={token1}"
    new_link = f"{base}{reverse('accounts:confirm_new')}?t={token2}"
    send_mail("Approve email change", f"Approve change: {old_link}", settings.DEFAULT_FROM_EMAIL, [request.user.email])
    send_mail("Verify new email", f"Verify address: {new_link}", settings.DEFAULT_FROM_EMAIL, [new_email])
    return HttpResponse("Change email initiated")

@login_required
def confirm_old(request):
    t = request.GET.get("t")
    if not t:
        return HttpResponseBadRequest("missing token")
    ecr = EmailChangeRequest.objects.filter(old_email_token=t, user=request.user, expires_at__gt=timezone.now()).first()
    if not ecr:
        return HttpResponseBadRequest("invalid token")
    ecr.confirmed_old = True
    ecr.save(update_fields=["confirmed_old"])
    _maybe_finalize_email_change(ecr, request)
    return HttpResponse("Old email confirmed")

@login_required
def confirm_new(request):
    t = request.GET.get("t")
    if not t:
        return HttpResponseBadRequest("missing token")
    ecr = EmailChangeRequest.objects.filter(new_email_token=t, user=request.user, expires_at__gt=timezone.now()).first()
    if not ecr:
        return HttpResponseBadRequest("invalid token")
    ecr.confirmed_new = True
    ecr.save(update_fields=["confirmed_new"])
    _maybe_finalize_email_change(ecr, request)
    return HttpResponse("New email confirmed")

def _maybe_finalize_email_change(ecr, request):
    if ecr.confirmed_old and ecr.confirmed_new:
        user = ecr.user
        user.email = ecr.new_email
        user.save(update_fields=["email"])
        EmailAddress.objects.update_or_create(user=user, email=user.email, defaults={"verified": True, "primary": True})
        EmailAddress.objects.filter(user=user).exclude(email=user.email).update(primary=False)
        update_session_auth_hash(request, user)
        ecr.delete()


@login_required
def alternate_emails(request):
    emails = (
        EmailAddress.objects.filter(user=request.user)
        .order_by("-primary", "-verified", "email")
    )
    return render(
        request,
        "accounts/alternate_emails.html",
        {"emails": emails, "active_nav": "preferences"},
    )

@login_required
def send_progress_now(request):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    pref = getattr(request.user, "email_pref", None)
    if not pref or not pref.marketing_opt_in:
        return redirect("accounts:preferences")
    cid = getattr(settings, "PROGRESS_CAMPAIGN_ID", "")
    campaign = None
    if cid:
        campaign = Campaign.objects.filter(pk=cid).first()
    if not campaign:
        campaign = Campaign.objects.filter(template__key="progress_update").first()
    if not campaign:
        campaign = Campaign.objects.filter(
            template__html_template_path="emails/progress_update.html"
        ).first()
    if not campaign:
        tmpl, _ = EmailTemplate.objects.get_or_create(
            key="progress_update",
            defaults={
                "subject_template": "Your weekly update",
                "html_template_path": "emails/progress_update.html",
                "text_template_path": "",
            },
        )
        campaign, _ = Campaign.objects.get_or_create(
            name="Progress Update",
            defaults={
                "template": tmpl,
                "enabled": True,
                "schedule_cron": "0 8 * * MON",
            },
        )
    MessageLog.objects.filter(campaign=campaign, user=request.user).delete()
    send_parent_update.delay(campaign.id, request.user.id)
    return redirect(reverse("accounts:preferences") + "?sent=1")
