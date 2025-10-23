from django.http import HttpResponse, HttpResponseBadRequest
from django.utils import timezone
from django.views.decorators.http import require_GET
from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
from accounts.models import EmailPreference, User

@require_GET
def unsubscribe(request):
    token = request.GET.get("t")
    if not token:
        return HttpResponseBadRequest("missing token")
    signer = TimestampSigner()
    try:
        user_id_str = signer.unsign(token, max_age=60 * 60 * 24 * 365)
        user_id = int(user_id_str)
    except (BadSignature, SignatureExpired, ValueError):
        return HttpResponseBadRequest("invalid token")
    user = User.objects.filter(pk=user_id).first()
    if not user:
        return HttpResponseBadRequest("invalid user")
    ep, _ = EmailPreference.objects.get_or_create(user=user)
    ep.marketing_opt_in = False
    ep.consent_source = "unsubscribe"
    ep.consent_timestamp = timezone.now()
    ep.save(update_fields=["marketing_opt_in", "consent_source", "consent_timestamp"])
    return HttpResponse("You have been unsubscribed.")
