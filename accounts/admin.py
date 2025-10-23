from django.contrib import admin
from .models import User, EmailPreference, EmailChangeRequest

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("id", "email", "is_active", "is_parent", "last_validated_at")
    search_fields = ("email",)

@admin.register(EmailPreference)
class EmailPreferenceAdmin(admin.ModelAdmin):
    list_display = ("user", "marketing_opt_in", "consent_source", "consent_timestamp")

@admin.register(EmailChangeRequest)
class EmailChangeRequestAdmin(admin.ModelAdmin):
    list_display = ("user", "new_email", "confirmed_old", "confirmed_new", "expires_at")
