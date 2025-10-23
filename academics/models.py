from django.db import models
from students.models import Student

class Term(models.Model):
    external_term_id = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=128)
    start_date = models.DateField()
    end_date = models.DateField()
    is_current = models.BooleanField(default=False)

class Module(models.Model):
    external_module_id = models.CharField(max_length=64, unique=True)
    code = models.CharField(max_length=32)
    title = models.CharField(max_length=200)
    credits = models.PositiveIntegerField(default=0)

class Enrollment(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    module = models.ForeignKey(Module, on_delete=models.CASCADE)
    term = models.ForeignKey(Term, on_delete=models.PROTECT)
    status = models.CharField(max_length=32, default="active")
    lecturer_name = models.CharField(max_length=128, blank=True)
    campus = models.CharField(max_length=128, blank=True)

class GradeItem(models.Model):
    STATUS_CHOICES = [("DRAFT","DRAFT"),("PUBLISHED","PUBLISHED")]
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE)
    name = models.CharField(max_length=128)
    weight = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    max_score = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    score = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="DRAFT")
    published_at = models.DateTimeField(null=True, blank=True)

class ExamSlot(models.Model):
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    venue = models.CharField(max_length=128, blank=True)
    seat = models.CharField(max_length=32, blank=True)
