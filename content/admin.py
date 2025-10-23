from django.contrib import admin
from .models import Announcement, ReadReceipt, Document

@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ("title", "severity", "audience", "published_at", "is_active")
    list_filter = ("severity", "audience", "category", "is_active")
    search_fields = ("title", "body_html")
    autocomplete_fields = ("to_user", "student", "module", "created_by")

@admin.register(ReadReceipt)
class ReadReceiptAdmin(admin.ModelAdmin):
    list_display = ("user", "announcement", "read_at")
    search_fields = ("user__email", "announcement__title")

@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "student", "category", "published_at", "is_public")
    list_filter = ("is_public", "category")
