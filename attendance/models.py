from django.db import models
from academics.models import Enrollment

class AttendanceRecord(models.Model):
    STATUS_CHOICES = [
        ("PRESENT","PRESENT"),
        ("ABSENT","ABSENT"),
        ("LATE","LATE"),
        ("EXCUSED","EXCUSED"),
    ]
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE)
    date = models.DateField()
    slot = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES)
    note = models.CharField(max_length=255, blank=True)
