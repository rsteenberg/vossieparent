import os
from dotenv import load_dotenv
from urllib.parse import urlparse
from pathlib import Path
from datetime import timedelta

BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env.
# We set override=True to keep .env as the single source of truth for app config
# in both local and server deployments, avoiding mismatches with inherited env.
load_dotenv(BASE_DIR / ".env", override=True)


def env_bool(name, default=False):
    val = os.environ.get(name)
    if val is None:
        return default
    return str(val).strip().lower() in ("1", "true", "yes", "on")


SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")
DEBUG = env_bool("DEBUG", True)
ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get("ALLOWED_HOSTS", "*").split(",")
    if h.strip()
]
CSRF_TRUSTED_ORIGINS = [
    o.strip()
    for o in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",")
    if o.strip()
]

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
    "axes",
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
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
)

# allauth (new-style settings)
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
LOGIN_REDIRECT_URL = "/"
LOGIN_URL = "account_login"
LOGOUT_REDIRECT_URL = "/"
ACCOUNT_FORMS = {"signup": "accounts.forms.SignupForm"}
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_USERNAME_REQUIRED = False
ACCOUNT_SESSION_REMEMBER = None
ACCOUNT_ADAPTER = "accounts.adapter.DevAccountAdapter"
ACCOUNT_RATE_LIMITS = {
    "login": "10/m/ip",
    "login_failed": "5/10m/key",
    "reset_password": "20/m/ip,5/m/key",
    "signup": "10/m/ip",
}

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "UserAttributeSimilarityValidator"
        )
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "MinimumLengthValidator"
        ),
        "OPTIONS": {"min_length": 8},
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "CommonPasswordValidator"
        )
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "NumericPasswordValidator"
        )
    },
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "axes.middleware.AxesMiddleware",
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
        "DIRS": [str(BASE_DIR / "templates")],
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

_DB_NAME = os.environ.get("DB_NAME")
if _DB_NAME:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": _DB_NAME,
            "USER": os.environ.get("DB_USER", ""),
            "PASSWORD": os.environ.get("DB_PASSWORD", ""),
            "HOST": os.environ.get("DB_HOST", "localhost"),
            "PORT": os.environ.get("DB_PORT", "5432"),
            "OPTIONS": (
                {"sslmode": os.environ.get("DB_SSLMODE", "")}
                if os.environ.get("DB_SSLMODE")
                else {}
            ),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": str(BASE_DIR / "db.sqlite3"),
        }
    }

_FABRIC_HOST = os.environ.get(
    "FABRIC_HOST",
    (
        "axlypt64epuevkdgi75usjh2pi-"
        "x4t7amu2lexe5c3dp4sy2tdgtu."
        "datawarehouse.fabric.microsoft.com"
    ),
)
_FABRIC_DB = os.environ.get("FABRIC_DB", "")
if _FABRIC_HOST and _FABRIC_DB:
    DATABASES["fabric"] = {
        "ENGINE": "mssql",
        "NAME": _FABRIC_DB,
        "HOST": f"{_FABRIC_HOST},1433",
        "USER": os.environ.get("DYN_CLIENT_ID", ""),
        "PASSWORD": os.environ.get("DYN_CLIENT_SECRET", ""),
        "OPTIONS": {
            "driver": "ODBC Driver 17 for SQL Server",
            "extra_params": "Authentication=ActiveDirectoryServicePrincipal",
        },
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

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "static_build"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

SESSION_COOKIE_AGE = 60 * 60 * 24 * 14
SESSION_COOKIE_SAMESITE = "Lax"
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", False)
_hsts = os.environ.get("SECURE_HSTS_SECONDS")
SECURE_HSTS_SECONDS = int(_hsts) if (_hsts and _hsts.isdigit()) else 0
if env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", False):
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
if env_bool("SECURE_HSTS_PRELOAD", False):
    SECURE_HSTS_PRELOAD = True
if env_bool("USE_X_FORWARDED_PROTO", False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

RQ_QUEUES = {
    "default": {
        "HOST": "localhost",
        "PORT": 6379,
        "DB": 0,
        "DEFAULT_TIMEOUT": 600,
    },
    "mail": {
        "HOST": "localhost",
        "PORT": 6379,
        "DB": 0,
        "DEFAULT_TIMEOUT": 600,
    },
}

# Email backend (Anymail if configured; fallback to console for dev)
SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY")
if SENDGRID_API_KEY:
    ANYMAIL = {"SENDGRID_API_KEY": SENDGRID_API_KEY}
    _sg_webhook_key = os.environ.get(
        "SENDGRID_TRACKING_WEBHOOK_VERIFICATION_KEY"
    )
    if _sg_webhook_key:
        ANYMAIL[
            "SENDGRID_TRACKING_WEBHOOK_VERIFICATION_KEY"
        ] = _sg_webhook_key
    EMAIL_BACKEND = "anymail.backends.sendgrid.EmailBackend"
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = os.environ.get(
    "DEFAULT_FROM_EMAIL", "Riaan Steenberg <riaan.steenberg@eduvos.com>"
)
SERVER_EMAIL = os.environ.get("SERVER_EMAIL", DEFAULT_FROM_EMAIL)
_admin_emails = os.environ.get("ADMIN_EMAILS", "")
_admin_name = os.environ.get("ADMIN_NAME", "Admin")
ADMINS = [
    (_admin_name, e.strip())
    for e in _admin_emails.split(",")
    if e.strip()
]

# Dynamics / Dataverse (server-to-server)
DYNAMICS_TENANT_ID = os.environ.get("DYN_TENANT_ID", "")
DYNAMICS_CLIENT_ID = os.environ.get("DYN_CLIENT_ID", "")
DYNAMICS_CLIENT_SECRET = os.environ.get("DYN_CLIENT_SECRET", "")
DYNAMICS_ORG_URL = os.environ.get("DYN_ORG_URL", "")
DYNAMICS_SCOPE = f"{DYNAMICS_ORG_URL}/.default" if DYNAMICS_ORG_URL else ""
DYNAMICS_PARENT_STUDENT_LINK_TABLE = os.environ.get(
    "DYN_PARENT_STUDENT_LINK_TABLE", ""
)
# Field (column logical name) on student Contact records that stores the sponsor/parent email
DYNAMICS_SPONSOR1_EMAIL_FIELD = os.environ.get(
    "DYN_SPONSOR1_EMAIL_FIELD", "btfh_sponsor1email"
)

# Identity lease
IDENTITY_LEASE_TTL_SECONDS = int(
    os.environ.get("IDENTITY_LEASE_TTL_SECONDS", "3600")
)

# Site URL for building absolute links
SITE_URL = os.environ.get("SITE_URL", "http://localhost:8000")
if SITE_URL.startswith("http://localhost:8000"):
    ACCOUNT_EMAIL_VERIFICATION = "none"

# Ensure SITE_URL host/origin are whitelisted even if env lists are missing
try:
    _parsed_site = urlparse(SITE_URL)
    _site_host = _parsed_site.hostname
    _site_origin = f"{_parsed_site.scheme}://{_parsed_site.hostname}"
    if _parsed_site.port and _parsed_site.port not in (80, 443):
        _site_origin = f"{_parsed_site.scheme}://{_parsed_site.hostname}:{_parsed_site.port}"
    if _site_host and _site_host not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(_site_host)
    if _parsed_site.scheme in ("http", "https") and _site_origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(_site_origin)
except Exception:
    pass

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "mail_admins": {
            "level": "ERROR",
            "class": "django.utils.log.AdminEmailHandler",
        },
    },
    "loggers": {
        "django.request": {
            "handlers": ["mail_admins"],
            "level": "ERROR",
            "propagate": True,
        },
        "django.security": {
            "handlers": ["mail_admins"],
            "level": "ERROR",
            "propagate": True,
        },
        "django.security.DisallowedHost": {
            "handlers": [],
            "level": "CRITICAL",
            "propagate": False,
        },
    },
}

AXES_ENABLED = True
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = timedelta(minutes=15)
AXES_LOCK_OUT_AT_FAILURE = True
AXES_LOCKOUT_PARAMETERS = ["username", "ip_address"]
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_TEMPLATE = "account/lockout.html"
