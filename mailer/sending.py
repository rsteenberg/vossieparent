from anymail.message import AnymailMessage
from django.urls import reverse
from django.core.signing import TimestampSigner
from django.conf import settings
from .rendering import render_email
from .models import MessageLog

def unsubscribe_link(user):
    signer = TimestampSigner()
    token = signer.sign(str(user.pk))
    return f"{settings.SITE_URL}{reverse('mailer:unsubscribe')}?t={token}"

def send_email_to_parent(campaign_id, user, context):
    from .models import Campaign
    campaign = Campaign.objects.get(pk=campaign_id)
    # idempotency: ensure only one message per (campaign, user)
    if MessageLog.objects.filter(campaign=campaign, user=user).exists():
        return
    template = campaign.template
    context = {**context, "unsubscribe_url": unsubscribe_link(user)}
    subject, text, html = render_email(template, context)
    msg = AnymailMessage(subject=subject, to=[user.email])
    if text:
        msg.body = text
    msg.attach_alternative(html, "text/html")
    msg.metadata = {"campaign_id": campaign_id, "user_id": user.id}
    msg.tags = [campaign.name]
    msg.send()
    provider_id = None
    try:
        provider_id = getattr(msg, "anymail_status", None).message_id
    except Exception:
        provider_id = None
    MessageLog.objects.get_or_create(campaign=campaign, user=user, defaults={"provider_id": provider_id})
