from django.contrib import admin
from .models import FeeAccount, Invoice, Payment

admin.site.register(FeeAccount)
admin.site.register(Invoice)
admin.site.register(Payment)
