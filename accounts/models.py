from django.contrib.auth.models import AbstractUser
from django.contrib.auth.base_user import BaseUserManager
from django.db import models
from django.utils import timezone

class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("The Email must be set")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email=None, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email=None, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(email, password, **extra_fields)

class User(AbstractUser):
    username = None
    email = models.EmailField(unique=True)
    is_parent = models.BooleanField(default=True)
    external_parent_id = models.CharField(max_length=64, blank=True, null=True)
    last_validated_at = models.DateTimeField(blank=True, null=True)
    EMAIL_FIELD = "email"
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []
    objects = UserManager()

class EmailPreference(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="email_pref")
    marketing_opt_in = models.BooleanField(default=False)
    consent_source = models.CharField(max_length=64, blank=True, null=True)
    consent_timestamp = models.DateTimeField(default=timezone.now)

class EmailChangeRequest(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    new_email = models.EmailField()
    old_email_token = models.CharField(max_length=64)
    new_email_token = models.CharField(max_length=64)
    confirmed_old = models.BooleanField(default=False)
    confirmed_new = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
