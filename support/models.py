from django.db import models

class Ticket(models.Model):
    CATEGORY_CHOICES = [("Academic","Academic"),("Financial","Financial"),("Technical","Technical")]
    STATUS_CHOICES = [("OPEN","OPEN"),("IN_PROGRESS","IN_PROGRESS"),("RESOLVED","RESOLVED")]
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE)
    student = models.ForeignKey("students.Student", null=True, blank=True, on_delete=models.SET_NULL)
    category = models.CharField(max_length=32, choices=CATEGORY_CHOICES)
    subject = models.CharField(max_length=200)
    body = models.TextField()
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="OPEN")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
