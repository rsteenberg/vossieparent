import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")
DEBUG = os.environ.get("DEBUG", "1") == "1"
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # third-party
    "django.contrib.sites",
    "allauth",
    "allauth.account",
    "django_rq",
    "anymail",
    "rest_framework",
    # local apps
    "accounts.apps.AccountsConfig",
    "students.apps.StudentsConfig",
    "crm.apps.CrmConfig",
    "mailer.apps.MailerConfig",
    "jobs.apps.JobsConfig",
    "academics.apps.AcademicsConfig",
    "attendance.apps.AttendanceConfig",
    "financials.apps.FinancialsConfig",
    "content.apps.ContentConfig",
    "support.apps.SupportConfig",
]

AUTH_USER_MODEL = "accounts.User"
SITE_ID = 1

AUTHENTICATION_BACKENDS = (
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
)

# allauth (new-style settings)
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
LOGIN_REDIRECT_URL = "/"
ACCOUNT_FORMS = {"signup": "accounts.forms.SignupForm"}

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # identity lease validation
    "accounts.middleware.IdentityLeaseMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "vossie-cache",
    }
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "static_build"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# RQ queues
RQ_QUEUES = {
    "default": {"HOST": "localhost", "PORT": 6379, "DB": 0, "DEFAULT_TIMEOUT": 600},
    "mail": {"HOST": "localhost", "PORT": 6379, "DB": 0, "DEFAULT_TIMEOUT": 600},
}

# Email backend (Anymail if configured; fallback to console for dev)
SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY")
if SENDGRID_API_KEY:
    ANYMAIL = {"SENDGRID_API_KEY": SENDGRID_API_KEY}
    EMAIL_BACKEND = "anymail.backends.sendgrid.EmailBackend"
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "School <no-reply@school.example>")

# Dynamics / Dataverse (server-to-server)
DYNAMICS_TENANT_ID = os.environ.get("DYN_TENANT_ID", "")
DYNAMICS_CLIENT_ID = os.environ.get("DYN_CLIENT_ID", "")
DYNAMICS_CLIENT_SECRET = os.environ.get("DYN_CLIENT_SECRET", "")
DYNAMICS_ORG_URL = os.environ.get("DYN_ORG_URL", "")
DYNAMICS_SCOPE = f"{DYNAMICS_ORG_URL}/.default" if DYNAMICS_ORG_URL else ""

# Identity lease
IDENTITY_LEASE_TTL_SECONDS = int(os.environ.get("IDENTITY_LEASE_TTL_SECONDS", "3600"))

# Site URL for building absolute links
SITE_URL = os.environ.get("SITE_URL", "http://localhost:8000")
