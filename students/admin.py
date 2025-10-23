from django.contrib import admin
from .models import Student, ParentStudentLink

@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("id", "external_student_id", "first_name", "last_name")
    search_fields = ("external_student_id", "first_name", "last_name")

@admin.register(ParentStudentLink)
class PSLAdmin(admin.ModelAdmin):
    list_display = ("user", "student", "active", "last_verified_at")
    list_filter = ("active",)
