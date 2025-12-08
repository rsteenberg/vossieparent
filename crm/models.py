from django.db import models

class Contact(models.Model):
    contact_id = models.CharField(max_length=64, unique=True, db_index=True)
    first_name = models.CharField(max_length=128, blank=True, null=True)
    last_name = models.CharField(max_length=128, blank=True, null=True)
    email = models.CharField(max_length=254, blank=True, null=True, db_index=True)
    sponsor1_email = models.CharField(max_length=254, blank=True, null=True, db_index=True)
    sponsor2_email = models.CharField(max_length=254, blank=True, null=True, db_index=True)
    
    # Store full row data from source table
    raw_data = models.JSONField(default=dict)
    
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.contact_id})"
