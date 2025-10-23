from anymail.signals import tracking
from django.dispatch import receiver
from .models import EmailEvent

@receiver(tracking)
def handle_tracking(sender, event, esp_name, **kwargs):
    EmailEvent.objects.create(
        user_id=event.metadata.get("user_id"),
        campaign_id=event.metadata.get("campaign_id"),
        event=event.event_type,
        provider_id=event.event_id,
        email=event.recipient,
        payload=event.esp_event,
    )
    if event.event_type in {"bounced", "complained"}:
        from accounts.models import User
        user_id = event.metadata.get("user_id")
        if user_id:
            user = User.objects.filter(id=user_id).first()
            if user and hasattr(user, "email_pref"):
                ep = user.email_pref
                ep.marketing_opt_in = False
                ep.save(update_fields=["marketing_opt_in"]) 
