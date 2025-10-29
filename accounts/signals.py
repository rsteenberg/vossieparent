from django.dispatch import receiver
from allauth.account.signals import user_logged_in
from django.db.models.signals import post_save
from django.conf import settings
from allauth.account.models import EmailAddress
from crm.service import validate_parent
from .models import EmailPreference, User


@receiver(user_logged_in)
def on_user_logged_in(sender, request, user, **kwargs):
    site = getattr(settings, "SITE_URL", "")
    if site.startswith("http://localhost:8000"):
        EmailAddress.objects.update_or_create(
            user=user,
            email=user.email,
            defaults={"verified": True, "primary": True},
        )
        EmailAddress.objects.filter(user=user).exclude(
            email=user.email
        ).update(primary=False)
    validate_parent(user)


@receiver(post_save, sender=User)
def ensure_email_pref(sender, instance, created, **kwargs):
    if created:
        EmailPreference.objects.get_or_create(user=instance)
