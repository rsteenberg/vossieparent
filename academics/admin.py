from django.contrib import admin
from .models import Term, Module, Enrollment, GradeItem, ExamSlot

admin.site.register(Term)

@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    search_fields = ("code", "title")
    list_display = ("code", "title", "credits")

admin.site.register(Enrollment)
admin.site.register(GradeItem)
admin.site.register(ExamSlot)
