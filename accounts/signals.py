from django.dispatch import receiver
from allauth.account.signals import user_logged_in
from django.db.models.signals import post_save
from crm.service import validate_parent
from .models import EmailPreference, User

@receiver(user_logged_in)
def on_user_logged_in(request, user, **kwargs):
    validate_parent(user)

@receiver(post_save, sender=User)
def ensure_email_pref(sender, instance, created, **kwargs):
    if created:
        EmailPreference.objects.get_or_create(user=instance)
