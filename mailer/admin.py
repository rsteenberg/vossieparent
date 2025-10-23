from django.contrib import admin
from .models import EmailTemplate, Campaign, EmailEvent, MessageLog

@admin.register(EmailTemplate)
class EmailTemplateAdmin(admin.ModelAdmin):
    list_display = ("id", "key", "subject_template")

@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "enabled", "schedule_cron", "last_run_at")
    list_filter = ("enabled",)

@admin.register(EmailEvent)
class EmailEventAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "campaign", "event", "email", "timestamp")
    list_filter = ("event",)

@admin.register(MessageLog)
class MessageLogAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "campaign", "sent_at", "provider_id")
    search_fields = ("user__email", "campaign__name", "provider_id")
