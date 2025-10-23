from django.contrib import admin
from .models import Ticket

@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "student", "category", "status", "created_at")
    list_filter = ("category", "status")
