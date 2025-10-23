from django.db import models
from django.conf import settings
from django.utils import timezone

class Student(models.Model):
    external_student_id = models.CharField(max_length=64, unique=True)
    first_name = models.CharField(max_length=64)
    last_name = models.CharField(max_length=64)

class ParentStudentLink(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    active = models.BooleanField(default=True)
    source = models.CharField(max_length=32, default="crm")
    last_verified_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        unique_together = [("user", "student")]
