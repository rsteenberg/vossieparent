import django_rq
from django_rq import job
from django.utils import timezone
from accounts.models import User
from mailer.models import Campaign
from mailer.sending import send_email_to_parent
from content.services import get_notice_buckets_for_user
from django.conf import settings

@job("default")
def kickoff_campaign(campaign_id: int):
    campaign = Campaign.objects.get(pk=campaign_id)
    if not campaign.enabled:
        return
    # mark last run time
    campaign.last_run_at = timezone.now()
    campaign.save(update_fields=["last_run_at"])
    qs = User.objects.filter(is_parent=True, email_pref__marketing_opt_in=True, is_active=True)
    batch_size = 1000
    ids = list(qs.values_list("id", flat=True))
    for i in range(0, len(ids), batch_size):
        enqueue_batch_send.delay(campaign_id, ids[i:i+batch_size])

@job("mail")
def enqueue_batch_send(campaign_id: int, user_ids: list[int]):
    for uid in user_ids:
        send_parent_update.delay(campaign_id, uid)

@job("mail")
def send_parent_update(campaign_id: int, user_id: int):
    from students.models import ParentStudentLink
    user = User.objects.get(pk=user_id)
    students = (
        ParentStudentLink.objects.select_related("student")
        .filter(user=user, active=True)
        .values_list("student__first_name", "student__last_name")
    )
    # notices digest for last 7 days
    buckets = get_notice_buckets_for_user(user, window_days=7)
    # cap to 5 per bucket for email digest
    capped = {k: v[:5] for k, v in buckets.items()}
    counts = {k: len(buckets[k]) for k in buckets}
    subject_vars = {
        "first": getattr(user, "first_name", "") or user.email,
        "personal_count": counts.get("personal", 0),
        "student_count": counts.get("student", 0),
        "module_count": counts.get("module", 0),
        "general_count": counts.get("general", 0),
        "total": sum(counts.values()),
    }
    context = {
        "parent": user,
        "students": list(students),
        "notices": capped,
        "notices_counts": counts,
        "subject_vars": subject_vars,
        "site_url": settings.SITE_URL,
    }
    send_email_to_parent(campaign_id, user, context)
