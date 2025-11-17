from django.dispatch import receiver
from allauth.account.signals import (
    user_logged_in,
    email_confirmed,
    email_added,
    email_removed,
    email_changed,
)
from django.db.models.signals import post_save, post_migrate
from django.conf import settings
from allauth.account.models import EmailAddress
from crm.service import validate_parent
from .models import EmailPreference, User
from urllib.parse import urlparse
from django.contrib.sites.models import Site


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


@receiver(post_save, sender=User)
def ensure_email_pref(sender, instance, created, **kwargs):
    if created:
        EmailPreference.objects.get_or_create(user=instance)


@receiver(post_migrate)
def sync_site_domain(sender, **kwargs):
    site_url = getattr(settings, "SITE_URL", "")
    if not site_url:
        return
    try:
        parsed = urlparse(site_url)
        host = parsed.hostname or "example.com"
        sid = getattr(settings, "SITE_ID", 1)
        Site.objects.update_or_create(
            id=sid, defaults={"domain": host, "name": host}
        )
    except Exception:
        # Best-effort, don't block migrations
        pass


@receiver(email_confirmed)
def on_email_confirmed(sender, request, email_address, **kwargs):
    # Refresh links when an address becomes verified
    user = getattr(email_address, "user", None)
    if user:
        validate_parent(user)


@receiver(email_added)
def on_email_added(sender, request, user, email_address, **kwargs):
    # Adding an alternate may create new Fabric matches
    validate_parent(user)


@receiver(email_removed)
def on_email_removed(sender, request, user, email_address, **kwargs):
    # Removal may drop matches; re-evaluate links
    validate_parent(user)


@receiver(email_changed)
def on_email_changed(
    sender, request, user, from_email_address, to_email_address, **kwargs
):
    # Primary change or update — re-evaluate links
    validate_parent(user)
