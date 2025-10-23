from django.db import models

class Announcement(models.Model):
    SEVERITY_CHOICES = [
        ("INFO", "INFO"),
        ("WARNING", "WARNING"),
        ("URGENT", "URGENT"),
    ]
    AUDIENCE_CHOICES = [
        ("ALL", "ALL"),
        ("PARENT", "PARENT"),
        ("STUDENT", "STUDENT"),
        ("MODULE", "MODULE"),
    ]

    title = models.CharField(max_length=200)
    body_html = models.TextField()
    category = models.CharField(max_length=64, blank=True)
    severity = models.CharField(
        max_length=16, choices=SEVERITY_CHOICES, default="INFO"
    )
    audience = models.CharField(
        max_length=16, choices=AUDIENCE_CHOICES, default="ALL"
    )
    to_user = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL
    )
    student = models.ForeignKey(
        "students.Student", null=True, blank=True, on_delete=models.SET_NULL
    )
    module = models.ForeignKey(
        "academics.Module", null=True, blank=True, on_delete=models.SET_NULL
    )
    published_at = models.DateTimeField()
    expires_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        "accounts.User",
        related_name="announcements_created",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )


class ReadReceipt(models.Model):
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE)
    announcement = models.ForeignKey(Announcement, on_delete=models.CASCADE)
    read_at = models.DateTimeField(auto_now_add=True)


class Document(models.Model):
    student = models.ForeignKey(
        "students.Student", null=True, blank=True, on_delete=models.CASCADE
    )
    title = models.CharField(max_length=200)
    category = models.CharField(max_length=64, blank=True)
    file_url = models.URLField()
    published_at = models.DateTimeField()
    expires_at = models.DateTimeField(null=True, blank=True)
    is_public = models.BooleanField(default=False)
