from django.db import models

class EmailTemplate(models.Model):
    key = models.SlugField(unique=True)
    subject_template = models.CharField(max_length=200)
    html_template_path = models.CharField(max_length=200)
    text_template_path = models.CharField(max_length=200, blank=True, null=True)

class Campaign(models.Model):
    name = models.CharField(max_length=128)
    template = models.ForeignKey(EmailTemplate, on_delete=models.PROTECT)
    enabled = models.BooleanField(default=False)
    schedule_cron = models.CharField(max_length=64)
    last_run_at = models.DateTimeField(blank=True, null=True)

class EmailEvent(models.Model):
    user = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True)
    campaign = models.ForeignKey(Campaign, on_delete=models.SET_NULL, null=True, blank=True)
    event = models.CharField(max_length=32)
    provider_id = models.CharField(max_length=128, blank=True, null=True)
    email = models.EmailField()
    timestamp = models.DateTimeField(auto_now_add=True)
    payload = models.JSONField(default=dict, blank=True)

class MessageLog(models.Model):
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE)
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE)
    sent_at = models.DateTimeField(auto_now_add=True)
    provider_id = models.CharField(max_length=128, blank=True, null=True)

    class Meta:
        unique_together = [("user", "campaign")]
