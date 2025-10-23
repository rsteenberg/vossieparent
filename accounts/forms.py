from allauth.account.forms import SignupForm as AllauthSignupForm
from django import forms
from .models import EmailPreference

class SignupForm(AllauthSignupForm):
    marketing_opt_in = forms.BooleanField(required=False, label="Receive progress updates")

    def save(self, request):
        user = super().save(request)
        ep, _ = EmailPreference.objects.get_or_create(user=user)
        ep.marketing_opt_in = bool(self.cleaned_data.get("marketing_opt_in"))
        ep.consent_source = "signup"
        ep.save()
        return user
