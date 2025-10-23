from django.db import models
from students.models import Student

class FeeAccount(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    external_account_id = models.CharField(max_length=64, unique=True)

class Invoice(models.Model):
    account = models.ForeignKey(FeeAccount, on_delete=models.CASCADE)
    external_invoice_id = models.CharField(max_length=64, unique=True)
    number = models.CharField(max_length=64)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    due_date = models.DateField()
    status = models.CharField(max_length=32)
    pdf_url = models.URLField(blank=True)

class Payment(models.Model):
    account = models.ForeignKey(FeeAccount, on_delete=models.CASCADE)
    external_payment_id = models.CharField(max_length=64, unique=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=32)
    provider_ref = models.CharField(max_length=128, blank=True)
    captured_at = models.DateTimeField()
