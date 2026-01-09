from django_rq import job
from django.utils import timezone
from accounts.models import User
from mailer.models import Campaign
from mailer.sending import send_email_to_parent
from .digest import build_weekly_digest
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


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
    user = User.objects.get(pk=user_id)
    digest = build_weekly_digest(user)
    context = {
        **digest,
        "parent": user,
        "site_url": settings.SITE_URL,
    }
    try:
        send_email_to_parent(campaign_id, user, context)
    except Exception:
        logger.exception(
            "send_parent_update failed",
            extra={"campaign_id": campaign_id, "user_id": user_id},
        )
        raise
