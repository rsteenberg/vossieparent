Below is a consolidated engineering build spec & coding instruction for the system we discussed: a Django‑based identity and comms service for parents, with login‑time validation against Dynamics 365 (Dataverse), opt‑in mailers, safe email‑change flows, and scheduled/batch delivery at scale (50k+). It’s organized so you can implement it module by module.

0) Goals & non‑goals

Goals

Separate “Parents Identity” surface from your core systems.

Authenticate parents locally; validate associations against Dynamics 365 at login time (“identity lease”).

Parents must explicitly opt‑in to mailers.

Robust email change process that prevents privilege escalation.

Scalable scheduled mail dispatch (50k+) with bounce/complaint tracking.

All sensitive provider calls from server‑side only (no front‑end exposure).

Non‑goals

No real‑time bidirectional sync with Dynamics.

No external low‑code orchestrator (n8n/Airflow) in the baseline—everything in Django + Django RQ.

1) High‑level architecture
[Parents Web/UI] ──> [Django app]
                        │
                        ├── Local auth (Django + allauth)
                        │
                        ├── “Identity lease” service
                        │     ↳ Validates against Dynamics at login (server-side OAuth)
                        │     ↳ Caches result for short TTL
                        │
                        ├── Mailer service (Anymail + ESP)
                        │     ↳ Templates (Django templates)
                        │     ↳ Opt-in/consent & preferences
                        │     ↳ Webhook receiver (bounces/complaints)
                        │
                        ├── Tasks & scheduling (Django RQ + rq-scheduler)
                        │     ↳ Campaign kickoff → batch fan-out → send jobs
                        │
                        └── Admin/ops (Django admin + django-rq dashboard)

2) Key Django apps & dependencies

Apps

accounts/ – user model, email-change flow, identity lease

students/ – Student, Parent↔Student linking

crm/ – Dynamics (Dataverse) Web API client

mailer/ – templates, campaigns, events, webhooks

jobs/ – RQ tasks and scheduling

Packages

django-allauth (email-first auth, email verification)

django-rq + rq-scheduler (background jobs + periodic schedules)

django-anymail (ESP integration; use SES, SendGrid, Mailgun, etc.)

msal (Azure AD OAuth for Dataverse)

djangorestframework (webhooks / APIs)

argon2-cffi (password hasher)

django-axes (optional: lockouts/rate limiting)

3) Settings (snippets)
# settings.py
INSTALLED_APPS += [
    "django.contrib.sites",
    "allauth", "allauth.account",
    "django_rq",
    "anymail",
    "rest_framework",
    # your local apps
    "accounts", "students", "crm", "mailer", "jobs",
]

AUTH_USER_MODEL = "accounts.User"  # custom user; see models below
SITE_ID = 1

# Allauth: email-first, verify on signup and email change
ACCOUNT_AUTHENTICATION_METHOD = "email"
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
LOGIN_REDIRECT_URL = "/"

# Argon2 for strong password hashing
PASSWORD_HASHERS = ["django.contrib.auth.hashers.Argon2PasswordHasher"]

# RQ
RQ_QUEUES = {
    "default": {"HOST": "localhost", "PORT": 6379, "DB": 0, "DEFAULT_TIMEOUT": 600},
    "mail":    {"HOST": "localhost", "PORT": 6379, "DB": 0, "DEFAULT_TIMEOUT": 600},
}
# If you use rq-scheduler, run its separate process and point it at the same Redis.

# Anymail (example for SendGrid; swap for your ESP)
ANYMAIL = {"SENDGRID_API_KEY": os.environ.get("SENDGRID_API_KEY")}
EMAIL_BACKEND = "anymail.backends.sendgrid.EmailBackend"
DEFAULT_FROM_EMAIL = "School <no-reply@school.example>"

# Dynamics / Dataverse (server-to-server)
DYNAMICS_TENANT_ID = os.environ["DYN_TENANT_ID"]
DYNAMICS_CLIENT_ID = os.environ["DYN_CLIENT_ID"]
DYNAMICS_CLIENT_SECRET = os.environ["DYN_CLIENT_SECRET"]
DYNAMICS_ORG_URL = os.environ["DYN_ORG_URL"]  # e.g., https://org.crm.dynamics.com
DYNAMICS_SCOPE = f"{os.environ['DYN_ORG_URL']}/.default"

# Identity lease
IDENTITY_LEASE_TTL_SECONDS = 3600  # 1 hour


urls.py:

urlpatterns = [
    path("admin/", admin.site.urls),
    path("django-rq/", include("django_rq.urls")),  # dashboard
    path("webhooks/email/", include("mailer.webhooks_urls")),
    # allauth URLs (login/logout/signup/confirm):
    path("accounts/", include("allauth.urls")),
]

4) Data model (core)
# accounts/models.py
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

class User(AbstractUser):
    username = None  # email-as-username
    email = models.EmailField(unique=True)
    is_parent = models.BooleanField(default=True)  # baseline: only parents here
    external_parent_id = models.CharField(max_length=64, blank=True, null=True)  # Dataverse contact id
    last_validated_at = models.DateTimeField(blank=True, null=True)  # for identity lease
    EMAIL_FIELD = "email"
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

class EmailPreference(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="email_pref")
    marketing_opt_in = models.BooleanField(default=False)  # your “mailer” consent
    # track consent provenance
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

# students/models.py
class Student(models.Model):
    external_student_id = models.CharField(max_length=64, unique=True)  # Dataverse id
    first_name = models.CharField(max_length=64)
    last_name = models.CharField(max_length=64)

class ParentStudentLink(models.Model):
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    active = models.BooleanField(default=True)
    source = models.CharField(max_length=32, default="crm")  # provenance
    last_verified_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        unique_together = [("user", "student")]

# mailer/models.py
from django.db import models

class EmailTemplate(models.Model):
    key = models.SlugField(unique=True)
    subject_template = models.CharField(max_length=200)
    html_template_path = models.CharField(max_length=200)  # e.g. "emails/progress_update.html"
    text_template_path = models.CharField(max_length=200, blank=True, null=True)

class Campaign(models.Model):
    name = models.CharField(max_length=128)
    template = models.ForeignKey(EmailTemplate, on_delete=models.PROTECT)
    enabled = models.BooleanField(default=False)
    schedule_cron = models.CharField(max_length=64)  # e.g., "0 8 * * MON"
    last_run_at = models.DateTimeField(blank=True, null=True)

class EmailEvent(models.Model):
    user = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True)
    campaign = models.ForeignKey(Campaign, on_delete=models.SET_NULL, null=True, blank=True)
    event = models.CharField(max_length=32)  # delivered, bounced, complained, opened, clicked, etc.
    provider_id = models.CharField(max_length=128, blank=True, null=True)
    email = models.EmailField()
    timestamp = models.DateTimeField(auto_now_add=True)
    payload = models.JSONField(default=dict, blank=True)

5) Identity lease: login‑time validation against Dynamics

[2025-10-30] Dynamics token failure handling (no login crash)
- Files: `crm/msal_client.py`, `crm/service.py`
- Behavior impact: If Dataverse/MSAL auth fails (e.g., invalid client secret), login proceeds without crashing; CRM validation is skipped for that request.
- Data model: none (migration: no)
- Integrations/Jobs: MSAL token acquisition now raises a specific exception; service layer swallows failures and returns False.
- Emails/Templates: none
- Security/Privacy: No secrets logged; guidance to rotate/fix client secret in Azure AD.
- Rollout/Flags: No flags. Deploy and ensure environment secret is valid.
- Links: 

Flow

Parent logs in (local Django credentials).

Immediately call Dataverse to validate:

Parent contact exists (by external_parent_id or by verified email).

Parent↔Student associations are current & active.

Cache a lease: set user.last_validated_at and update ParentStudentLink rows.

Middleware guards high‑risk views: if now - last_validated_at > TTL, re‑validate (silent server call). If invalid, revoke access to student data (and optionally log the user out).

Dynamics client (server‑side only)

# crm/msal_client.py
import msal, requests, time
from django.conf import settings
from django.core.cache import cache

TOKEN_CACHE_KEY = "dyn_app_token"

def get_app_token():
    cached = cache.get(TOKEN_CACHE_KEY)
    if cached and cached["expires_at"] > time.time() + 30:
        return cached["access_token"]
    app = msal.ConfidentialClientApplication(
        client_id=settings.DYNAMICS_CLIENT_ID,
        client_credential=settings.DYNAMICS_CLIENT_SECRET,
        authority=f"https://login.microsoftonline.com/{settings.DYNAMICS_TENANT_ID}",
    )
    result = app.acquire_token_for_client(scopes=[settings.DYNAMICS_SCOPE])
    token = result["access_token"]
    cache.set(TOKEN_CACHE_KEY, {"access_token": token, "expires_at": time.time() + result["expires_in"] - 30}, result["expires_in"])
    return token

def dyn_get(path, params=None):
    token = get_app_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "OData-MaxVersion": "4.0",
        "OData-Version": "4.0",
        "Accept": "application/json",
    }
    url = f"{settings.DYNAMICS_ORG_URL}/api/data/v9.2/{path.lstrip('/')}"
    r = requests.get(url, headers=headers, params=params, timeout=20)
    r.raise_for_status()
    return r.json()

# crm/service.py
from accounts.models import User
from students.models import Student, ParentStudentLink
from django.utils import timezone

def validate_parent(user: User) -> bool:
    """
    Look up the parent's contact and their student link(s) in Dataverse.
    Update local links; return True if at least one active link exists.
    """
    # Example: by external id if stored; otherwise by verified email
    if user.external_parent_id:
        contact = dyn_get(f"contacts({user.external_parent_id})")
    else:
        # NOTE: replace filter with your actual schema/fields
        res = dyn_get("contacts", params={"$select": "contactid,emailaddress1,firstname,lastname",
                                          "$filter": f"emailaddress1 eq '{user.email}'"})
        values = res.get("value", [])
        contact = values[0] if values else None

    if not contact:
        return False

    # Resolve student relationships via your Dataverse schema (examples below are placeholders):
    # e.g., custom relationship table: new_parentstudentlinks where _parentid_value == contactid
    links = dyn_get("new_parentstudentlinks", params={"$filter": f"_parentid_value eq {contact['contactid']} and statecode eq 0"})
    active_students = []
    for row in links.get("value", []):
        external_student_id = row["_studentid_value"]
        st, _ = Student.objects.get_or_create(external_student_id=external_student_id)
        ParentStudentLink.objects.update_or_create(
            user=user, student=st, defaults={"active": True, "last_verified_at": timezone.now()}
        )
        active_students.append(st.id)

    # Deactivate stale links locally
    ParentStudentLink.objects.filter(user=user).exclude(student_id__in=active_students).update(active=False)

    user.external_parent_id = contact["contactid"]
    user.last_validated_at = timezone.now()
    user.save(update_fields=["external_parent_id", "last_validated_at"])
    return bool(active_students)


Where to call validation

On login success (allauth signal): user_logged_in → validate_parent(user)

Middleware for protected views (re‑validate if lease expired).

6) Preventing email‑change privilege escalation

Principles

Never use email as the authorization join key to students. Use stable external IDs from Dataverse.

Lock down email change with two‑party confirmation:

Confirm via old email and 2) verify new email.

Optional admin approval for sensitive cases.

Implementation outline

Provide a “Change email” view that creates EmailChangeRequest with two tokens.

Send one message to the old address (“Approve change”) and one to the new address (“Verify address”).

When both tokens are confirmed (and within expiry), update user.email and allauth EmailAddress entries; re‑issue session.

7) Opt‑in & preferences

On registration, show a checkbox for “receive progress updates” → set EmailPreference.marketing_opt_in=True and collect consent metadata.

Expose a preferences page and an unsubscribe link in every email (see §10).

8) Email authoring & templating

Use Django templates stored under templates/emails/….

Keep HTML and plain text versions.

Context building should aggregate all of a parent’s active students for that send.

# mailer/rendering.py
from django.template.loader import render_to_string

def render_email(template, context):
    subject = template.subject_template.format(**context.get("subject_vars", {}))
    html_body = render_to_string(template.html_template_path, context)
    text_body = render_to_string(template.text_template_path, context) if template.text_template_path else None
    return subject, text_body, html_body

9) Scheduled sends at scale (Django RQ)

Patterns

Orchestrator job (per campaign schedule) selects recipients and enqueues batch jobs (e.g., batches of 500–1,000).

Batch job builds context and enqueues send jobs per recipient, or uses ESP bulk API if available.

Respect ESP rate limits; configure queue concurrency for throughput (e.g., 5–20 workers on mail queue).

# jobs/tasks.py
import django_rq
from django_rq import job
from django.db.models import Q
from django.utils import timezone
from mailer.models import Campaign
from accounts.models import User
from mailer.sending import send_email_to_parent

@job("default")  # orchestrator
def kickoff_campaign(campaign_id: int):
    campaign = Campaign.objects.get(pk=campaign_id)
    qs = User.objects.filter(is_parent=True, email_pref__marketing_opt_in=True, is_active=True)
    # shard recipients
    batch_size = 1000
    ids = list(qs.values_list("id", flat=True))
    for i in range(0, len(ids), batch_size):
        enqueue_batch_send.delay(campaign_id, ids[i:i+batch_size])

@job("mail")
def enqueue_batch_send(campaign_id: int, user_ids: list[int]):
    for uid in user_ids:
        send_parent_update.delay(campaign_id, uid)

@job("mail")
def send_parent_update(campaign_id: int, user_id: int):
    # Build personalized context (all active students for this parent)
    user = User.objects.get(pk=user_id)
    from students.models import ParentStudentLink
    students = (
        ParentStudentLink.objects.select_related("student")
        .filter(user=user, active=True)
        .values_list("student__first_name", "student__last_name")
    )
    context = {"parent": user, "students": list(students)}
    send_email_to_parent(campaign_id, user, context)


Scheduling (cron‑like)

Use rq-scheduler or django-rq’s scheduler integration to register repeating jobs per Campaign.schedule_cron (e.g., “0 8 * * MON”).

Keep a small management command that (re)applies schedules from DB to the scheduler on deploy.

10) Sending + unsubscribe + idempotency
# mailer/sending.py
from anymail.message import AnymailMessage
from django.urls import reverse
from django.core.signing import TimestampSigner, BadSignature

def unsubscribe_link(user):
    signer = TimestampSigner()
    token = signer.sign(str(user.pk))
    return f"{settings.SITE_URL}{reverse('mailer:unsubscribe')}?t={token}"

def send_email_to_parent(campaign_id, user, context):
    from mailer.models import Campaign
    campaign = Campaign.objects.get(pk=campaign_id)
    template = campaign.template
    context = {**context, "unsubscribe_url": unsubscribe_link(user)}
    subject, text, html = render_email(template, context)

    msg = AnymailMessage(subject=subject, to=[user.email])
    if text: msg.body = text
    msg.attach_alternative(html, "text/html")
    # idempotency: set a custom header with campaign+user to dedupe at ESP if supported
    msg.metadata = {"campaign_id": campaign_id, "user_id": user.id}
    msg.tags = [campaign.name]
    msg.send()


Unsubscribe view

Parse and verify the signed token, set marketing_opt_in=False, store timestamp/source.

11) Delivery events (bounces/complaints) via webhooks

Use Anymail’s tracking signals to get provider‑agnostic events.

On bounce/complaint → mark the user as needs_attention or auto‑disable opt‑in until details are corrected.

# mailer/signals.py
from anymail.signals import tracking
from django.dispatch import receiver
from mailer.models import EmailEvent

@receiver(tracking)
def handle_tracking(sender, event, esp_name, **kwargs):
    EmailEvent.objects.create(
        user_id=event.metadata.get("user_id"),
        campaign_id=event.metadata.get("campaign_id"),
        event=event.event_type,  # "bounced", "complained", "delivered", ...
        provider_id=event.event_id,
        email=event.recipient,
        payload=event.esp_event,
    )
    if event.event_type in {"bounced", "complained"}:
        # optional: auto-disable mailer for this user, and/or create a “follow up” case
        from accounts.models import EmailPreference, User
        if event.metadata.get("user_id"):
            user = User.objects.filter(id=event.metadata["user_id"]).first()
            if user and hasattr(user, "email_pref"):
                ep = user.email_pref
                ep.marketing_opt_in = False
                ep.save(update_fields=["marketing_opt_in"])


urls for webhooks (Anymail provides provider‑specific webhook views you can include; alternatively expose a DRF endpoint and pass events through to the signal handler).

12) Admin/ops UX

Django admin:

Users, Students, ParentStudentLink (readonly external IDs)

EmailPreference (consent audit)

Campaigns & EmailTemplates

EmailEvent (filters by event type)

django-rq dashboard at /django-rq/:

Monitor queues, failed jobs, requeue, schedule.

13) Access control & object‑level checks

Views that expose student data must filter by ParentStudentLink.active=True and current user.

Add a permission helper:

def parent_can_view_student(user, student_id) -> bool:
    if not user.is_authenticated or not user.is_parent:
        return False
    # re-check lease (optional middleware can do this centrally)
    from django.utils import timezone
    ttl = settings.IDENTITY_LEASE_TTL_SECONDS
    if not user.last_validated_at or (timezone.now() - user.last_validated_at).total_seconds() > ttl:
        from crm.service import validate_parent
        if not validate_parent(user):
            return False
    return ParentStudentLink.objects.filter(user=user, student_id=student_id, active=True).exists()


Use this guard (or a decorator) anywhere student data is served.

14) Performance/scale guidelines (50k+)

Use batch fan‑out with RQ; choose a mail queue with multiple workers.

Set ESP rate limits (per minute) and use worker concurrency accordingly.

Fetch parents using .only("id","email") or .values_list(...) to minimize ORM overhead.

For content that’s identical (e.g., school‑wide newsletter), use ESP bulk send when available.

Idempotency: ensure one message per (campaign, user). Store a MessageLog or use ESP metadata and dedupe before sending.

Retry with backoff on transient ESP errors.

15) Security considerations

All Dynamics/Dataverse traffic only from server-side using msal client credentials.

Store secrets in environment variables; rotate regularly.

CSRF on forms; session cookies HttpOnly, Secure, SameSite=Lax/Strict.

Brute force protection with django-axes (optional).

Audit log: email change attempts, lease validation failures, webhook events.

16) Testing checklist

Unit tests for:

validate_parent() happy/edge cases (mock Dataverse responses).

Email change double‑confirmation flow (tokens, expiry).

Unsubscribe link validity and tamper resistance.

Permission guard on student data.

Integration tests:

Full campaign run on a small fixture set.

Webhook processing (bounce → opt‑out).

17) Minimal implementation sequence (checklist)

Project setup: custom User, allauth config, Argon2.

Models: Student, ParentStudentLink, EmailPreference.

Dynamics client (msal_client.py) and validate_parent() service.

Login hook: connect user_logged_in to validate_parent(); add middleware for TTL renewals.

Email change flow with two‑party confirmation.

Mailer: templates + rendering; Campaign, EmailEvent.

Jobs: RQ queues; implement kickoff_campaign → enqueue_batch_send → send_parent_update.

Scheduler: provision rq-scheduler; cron schedules from Campaign.schedule_cron.

Webhooks: Anymail tracking signal ⇢ persist events; auto‑opt‑out on bounce/complaint.

Admin & dashboard: register models; enable /django-rq/.

Scale tune: batch size, worker count, rate limits, idempotency.

18) Example email template (HTML)
<!-- templates/emails/progress_update.html -->
<!doctype html>
<html>
  <body>
    <p>Hi {{ parent.first_name|default:"there" }},</p>
    <p>Here’s this week’s update for {% if students|length == 1 %}your child{% else %}your children{% endif %}:</p>
    <ul>
      {% for first,last in students %}
        <li><strong>{{ first }} {{ last }}</strong>: progress summary goes here…</li>
      {% endfor %}
    </ul>
    <p>If you no longer wish to receive these, you can
      <a href="{{ unsubscribe_url }}">unsubscribe here</a>.</p>
  </body>
</html>

Notes & adaptations

Dataverse schema: Replace the placeholder table/field names with your actual environment (e.g., whether students are contacts, a custom table, or whether the relationship is via a custom N:N table). Keep the same pattern: resolve parent contact → fetch active student links → update local links.

ESP choice: Anymail abstracts providers. Start with one (SES/SendGrid/Mailgun) and switch later without rewriting business logic.

Alternative queues: You can swap RQ with Celery later; the orchestration pattern (kickoff → batch → send) remains identical.

---

# Part II — Eduvos Parent Portal (Product + Engineering Spec)

This section extends the identity and comms baseline (Part I) into a fully featured Eduvos Parent Portal. It defines product scope, UX, backend data model, integrations, and operational/non‑functional requirements to take the portal to production.

0) Purpose & outcomes

- Give parents/guardians a secure, self‑service view of their students’ academic progress, attendance, timetables, financials, and official communications.
- Reduce calls to support by enabling self‑service profile updates, preferences, and document downloads.
- Respect POPIA with explicit consent, least privilege, and full auditability.

1) Scope (features)

- Authentication & account
  - Email‑first login with verification (allauth) and identity lease against Dataverse (Part I).
  - Multi‑student switcher for parents linked to more than one student.
  - Email change with double confirmation (Part I). Preferences/consent management.

- Home/Dashboard
  - Welcome header with parent name; student switch control.
  - Cards: Attendance (YTD %, last 7 days), Grades (latest results), Timetable (today), Financials (balance snapshot), Notices.
  - Quick actions: Preferences, Change email, Download statement, Contact support.

- Academics
  - Modules/Courses for active term with credit, lecturer, campus info.
  - Grades per assessment item and module final where available; status: Draft/Published.
  - Timetable (week view) incl. room/venue; Exam schedule.
  - Progress report download (PDF) when published.

- Attendance
  - Daily/period attendance summary (Present/Absent/Late/Excused) with filters by date range and module.
  - Aggregate KPIs with visual trend.

- Financials
  - Account summary: balance, aging buckets.
  - Invoices/Statements listing (PDF download). Payments history.
  - Future: Online payment integration (gateway) with reconciliation (out of baseline; see §10).

- Communications
  - Announcements and notices from Eduvos (with categories and read/unread).
  - Email preferences (Part I) and unsubscribe link in all mailers.

- Documents
  - Official docs (policies, guides) and student documents (letters, certificates) exposed for download based on availability.

- Support
  - Submit a support request/ticket; optional category (Academic/Financial/Technical).
  - Auto‑acknowledge mail and admin queue in Django admin.

2) IA/Navigation (baseline)

- Top‑level: Dashboard, Academics, Attendance, Financials, Documents, Support, Settings.
- Student switcher persistent in header when >1 linked student.
- Root “/” shows login when logged out; shows Dashboard when logged in (baseline implemented in app).

3) Data model (portal additions)

Note: Keep authoritative IDs from upstream systems (Dataverse/SIS/Finance). All models below are additive to Part I.

```text
students/
  Student (existing): external_student_id, first_name, last_name
  ParentStudentLink (existing): user, student, active, last_verified_at

academics/
  Term: external_term_id, name, start_date, end_date, is_current
  Module: external_module_id, code, title, credits
  Enrollment: student(FK), module(FK), term(FK), status, lecturer_name, campus
  GradeItem: enrollment(FK), name, weight, max_score, score, percentage, status(DRAFT|PUBLISHED), published_at
  ExamSlot: enrollment(FK), starts_at, ends_at, venue, seat

attendance/
  AttendanceRecord: enrollment(FK), date, slot(optional), status(PRESENT|ABSENT|LATE|EXCUSED), note

financials/
  FeeAccount: student(FK), external_account_id
  Invoice: account(FK), external_invoice_id, number, amount, due_date, status, pdf_url
  Payment: account(FK), external_payment_id, amount, status, provider_ref, captured_at

content/
  Announcement: title, body_html, category, severity, published_at, expires_at, is_active, audience(ALL|PARENT|STUDENT|MODULE), to_user(FK optional), student(FK optional), module(FK optional), created_by(FK user)
  ReadReceipt: user(FK), announcement(FK), read_at
  Document: student(FK optional), title, category, file_url, published_at, expires_at, is_public

support/
  Ticket: user(FK), student(FK optional), category, subject, body, status, created_at, updated_at

compliance/
  ConsentRecord: user(FK), key, value(bool/JSON), source, timestamp
  AuditLog: actor_user(FK), action, target_model, target_id, meta(JSON), at
```

4) Integrations & data flows

- Source systems
  - Parent↔Student, Person master: Dataverse (D365). Already used for identity lease.
  - Academics (enrolments, grades, attendance, timetable): SIS (Dataverse tables or separate API). Define exact tables/fields in environment mapping doc.
  - Financials (invoices, statements, payments): Finance system (ERP/Dataverse). Provide REST endpoints or shared file drops.

- Sync strategy
  - Nightly and on‑demand deltas using background jobs (Django RQ). Favor snapshot pulls with updated_since filtering.
  - Idempotent upserts by external IDs. Never try to “own” upstream data in portal DB.

- Authentication to providers
  - Dataverse via `msal` client credentials (Part I).
  - Other systems via server‑to‑server OAuth2 or signed webhook/file exchange.

5) Backend services (Django apps)

- Recommended app split (alongside Part I): `academics/`, `attendance/`, `financials/`, `content/`, `support/`.
- Each app exposes:
  - Models (as above), admin registrations, serializers (DRF), and query services.
  - Read‑only views for parents guarded with `parent_can_view_student()` (Part I §13) and/or a decorator.
  - Importers: idempotent upserts from provider JSON payloads.

6) Views/Pages (baseline HTML, upgradable to templates later)

- Dashboard: aggregates quick stats for selected student.
- Academics: list of modules → module detail (assessments, grades, exam slot).
- Attendance: day/period table + filters; summary aggregates.
- Financials: account summary, invoices list (download PDF), payments list.
- Documents: available documents filtered by student/visibility.
- Support: new ticket form + status list; emails on update.
- Settings: Email preferences and change email (already implemented), logout.

7) Access control

- All student‑scoped endpoints call `parent_can_view_student(user, student_id)`; for list pages, filter by linked students only.
- Keep object‑level checks in queryset builders to avoid mistakes in templates.
- Lease TTL revalidation via middleware (Part I) before accessing sensitive endpoints.

8) APIs (internal)

- Use small DRF serializers/viewsets for async widgets if needed (e.g., dashboard cards). Keep server‑rendered HTML for baseline.
- Example read‑only endpoints (all guarded):
  - GET /api/students/{id}/enrollments/ → modules + lecturer + term
  - GET /api/enrollments/{id}/grades/ → grade items
  - GET /api/students/{id}/attendance?from=&to= → records + aggregates
  - GET /api/students/{id}/financials/invoices/ → invoices

9) Background jobs (RQ)

- Schedulers: nightly 02:00 local time: pull enrollments, grades (published only), attendance, invoices, payments.
- Tasks:
  - sync_enrollments(term) → upsert Enrollments/Modules/Terms.
  - sync_grades(term) → upsert GradeItems with status.
  - sync_attendance(range) → upsert AttendanceRecord.
  - sync_financials(range) → upsert invoices/payments and pre‑sign statement URLs if needed.
- Metrics: counters for created/updated/skipped and error logs per job run.

10) Financials (payments)

- Baseline: read‑only view of invoices/payments; statement/invoice PDFs via provider URL.
- Future: card/eFT payments via a gateway (e.g., PayGate, PayFast). Pattern:
  - Create PaymentIntent record → redirect to gateway → webhook confirms → reconcile to Payment and optionally POST back to Finance.
  - Security: webhook signatures verification, replay protection, idempotent updates.

11) Security, privacy, compliance

- POPIA alignment: consent capture, purpose limitation, data minimisation, and rights to opt‑out of marketing.
- All provider calls server‑side; no secrets in browser.
- CSRF on forms; session cookie HttpOnly, Secure, SameSite=Lax/Strict (per environment); strong password hashing (Argon2).
- Brute force protection with django-axes (optional but recommended).
- Audit trails: Email change events, validations, login events, data exports/downloads, unsubscribe actions.

12) Performance & SLAs

- Expected parent base: 50k+; concurrent users modest outside peak periods (term starts, grade releases).
- Read patterns dominate; use select_related/values_list and only() to minimise ORM overhead.
- Cache static content and configuration (announcements list) with short TTLs.

13) Admin & operations

- Django admin: manage Announcements, Documents, Tickets; view read receipts and message logs.
- django-rq dashboard: monitor sync jobs and campaign sends.
- Feature flags in DB or settings to stage pages (e.g., hide Financials until ready).

14) Rollout plan (phased)

- Phase 1: Auth + Dashboard + Academics + Preferences + Unsubscribe + Campaigns.
- Phase 2: Attendance + Financials (read‑only) + Documents.
- Phase 3: Support tickets + Online payments + Advanced notifications.

15) Testing

- Unit: permission guards, importers, serializers, view logic.
- Integration: end‑to‑end flows for login → dashboard; sync tasks with provider mocks.
- Security: CSRF, unsubscribe tampering, email change flow, webhook signature verification (for payments).

16) UX & accessibility

- WCAG‑aware markup; keyboard accessible forms; clear error/success states.
- Mobile‑first responsive layout.

17) Open items to confirm with Eduvos

- Exact Dataverse/SIS table and field mappings for enrollments/grades/attendance.
- Finance system endpoints for invoices/statements and payments (if any).
- Branding and UI theme; content style for announcements.

18) Notices (targeting, UI, and email digest)

- Audience types and routing
  - Personal to parent: staff → specific parent (Announcement.to_user=user).
  - Student‑scoped: message about a specific student (Announcement.student in parent’s linked students).
  - Course/module‑scoped: message tied to a module (Announcement.module in the parent’s student enrollments).
  - General to parents: broad notices (Announcement.audience in {ALL,PARENT}).
  - All notices respect is_active, published_at/expires_at.

- Data model (additions clarified)
  - Announcement.severity: INFO|WARNING|URGENT (badge styling).
  - Announcement.audience: ALL|PARENT|STUDENT|MODULE with optional selectors: to_user, student, module.
  - ReadReceipt(user, announcement, read_at) for “unread” state.

- UI buckets (Announcements page)
  - Show 4 clearly separated sections with counts:
    1) Personal messages to you
    2) Notices about your student(s)
    3) Course/module notices
    4) General notices for parents
  - Each item: title, severity badge, published_at, issuer (created_by), short HTML preview.
  - Filters: severity, date range, student selector when >1.
  - Mark as read on click (create ReadReceipt).

- Email reminders (digest)
  - Weekly/daily digest includes the same 4 buckets; subject e.g. “Your weekly Eduvos notices”.
  - Each bucket included only if it has items (limit N, e.g., 5 per bucket; link to Announcements page for more).
  - Template styling similar to site; unsubscribe link included.  
   - Security/Privacy
    - Detail view permission checks per audience; read receipts created only for authorized users.
    - Rollout/Flags
    - Migrate DB, register EmailTemplate + Campaign, author sample announcements in admin.

Admin/ops
  - Admin can author announcements with audience and selectors.
  - List filters by severity, category, audience; search by title/body.
  - Metrics: sent/read counts via ReadReceipt.

---
# Changelog

- [2025-10-28] Confirmation links use application URL (SITE_URL)
  - Files changed
    - `accounts/views.py`
  - Behavior impact
    - Email change confirmation links now use the configured application URL from `SITE_URL` instead of deriving from the incoming request. This ensures correct host in emails behind proxies/CDNs or when triggered from background jobs.
  - Data model
    - None.
  - Integrations/Jobs
    - None.
  - Emails/Templates
    - No changes.
  - Security/Privacy
    - Reduces risk of incorrect domain leakage when requests originate through alternate hosts.
  - Rollout/Flags
    - Set `SITE_URL` in `.env` (e.g., `https://parents.eduvos.com`).
  - Links
    - N/A

- [2025-10-28] Students listing via Dynamics sponsor + MSAL authority fix
  - Files changed
    - `crm/msal_client.py`, `crm/service.py`
  - Behavior impact
    - Parents visiting the Students page now see all active linked students fetched from Dataverse via server-to-server OAuth.
    - If explicit parent↔student link rows are found in Dataverse (`new_parentstudentlinks`), those are used.
    - If no explicit links are found, the system falls back to students whose `edv_sponsoremail1` equals the parent’s email (Sponsor 1 Email), linking them locally.
    - Student first/last names are refreshed from Dataverse contacts when available.
  - Data model
    - No changes. Existing `Student` and `ParentStudentLink` are used.
  - Integrations/Jobs
    - Dataverse Web API queries: `contacts` and `new_parentstudentlinks`.
    - MSAL authority now uses configured tenant ID (`DYN_TENANT_ID`).
  - Emails/Templates
    - No changes.
  - Security/Privacy
    - Server-to-server OAuth using application user; no secrets in client.
    - Identity lease TTL governs revalidation frequency.
  - Rollout/Flags
    - Set env vars: `DYN_TENANT_ID`, `DYN_CLIENT_ID`, `DYN_CLIENT_SECRET`, `DYN_ORG_URL`.
    - Ensure the application user in Dataverse has read access to `contacts` and the custom link table.
    - Deploy and restart service.
  - Links
    - N/A

- [2025-10-28] Dynamics client helpers (POST/PATCH/DELETE, annotations)
  - Files changed
    - `crm/msal_client.py`
  - Behavior impact
    - No spec impact. Adds helper methods `dyn_post`, `dyn_patch`, `dyn_delete` and optional annotations flag to `dyn_get` for Dataverse API usage.
  - Data model
    - None.
  - Integrations/Jobs
    - Reuses existing MSAL client credentials and shared token cache; consistent with `DYNAMICS_*` settings.
  - Emails/Templates
    - None.
  - Security/Privacy
    - No changes. Still server-to-server OAuth with app registration.
  - Rollout/Flags
    - None.

- [2025-10-27] PostgreSQL database config via .env + lockout page
  - Files changed
    - `config/settings.py`
    - `requirements.txt`
    - `templates/account/lockout.html`
  - Behavior impact
    - When `.env` defines `DB_NAME`, the app uses PostgreSQL with the provided `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, and `DB_SSLMODE`. When absent, it falls back to SQLite.
    - Locked-out users now see a friendly lockout screen instead of a plain response.
  - Data model
    - No model changes. Migrations apply to create/update third-party tables (Axes) in the new database.
  - Integrations/Jobs
    - None.
  - Emails/Templates
    - New template `account/lockout.html` for lockout page.
  - Security/Privacy
    - DB credentials are sourced from `.env`. TLS is configurable via `DB_SSLMODE`.
  - Rollout/Flags
    - Install dependencies: `psycopg2-binary`.
    - Ensure PostgreSQL is running and credentials are set in `.env`.
    - Run `python manage.py migrate` against the PostgreSQL database.
  - Links
    - N/A

- [2025-10-27] Login security hardening (Axes, rate limits, validators, session cookies)
  - Files changed
    - `config/settings.py`
  - Behavior impact
    - Brute-force protection: 5 failed login attempts lock the account for 15 minutes (HTTP 429 on further attempts).
    - Login rate limiting via allauth: `login` (10/min/IP) and `login_failed` (5/10min/email).
    - Remember-me respected: sessions persist up to 14 days when selected; otherwise expire on browser close.
    - Explicit auth redirects (`LOGIN_URL`, `LOGOUT_REDIRECT_URL`) for consistency.
    - Secure cookies in production: `SESSION_COOKIE_SECURE` and `CSRF_COOKIE_SECURE` when `DEBUG=False`; `SameSite=Lax`.
  - Data model
    - Third-party app `django-axes` adds its own tables (migration: yes).
  - Jobs/Integrations
    - None.
  - Emails/Templates
    - None.
  - Security/Privacy
    - Axes lockouts + allauth rate limits reduce credential stuffing and brute-force risk.
    - Password validators enforce minimum complexity.
    - Session cookie security tightened in production.
  - Rollout/Flags
    - Run DB migrations to create Axes tables: `python manage.py migrate`.
    - If behind a reverse proxy, configure Axes/IPWare proxy settings (`AXES_IPWARE_PROXY_*`) accordingly.
    - No feature flags.
  - Links
    - N/A

- [2025-10-27] Automatic .env loading (python-dotenv)
  - Files changed
    - `requirements.txt`
    - `manage.py`
    - `config/wsgi.py`
    - `config/asgi.py`
  - Behavior impact
    - A `.env` file at the project root is automatically loaded for CLI (`manage.py`) and server processes (WSGI/ASGI). Environment variables like `SENDGRID_API_KEY`, `DEFAULT_FROM_EMAIL`, `SERVER_EMAIL`, `ADMIN_EMAILS`, etc., are now read consistently on startup.
  - Data model
    - No changes.
  - Jobs/Integrations
    - None.
  - Emails/Templates
    - No changes; ensures SendGrid config is read without relying on OS shell env.
  - Security/Privacy
    - `.env` remains gitignored; store secrets only in `.env` or systemd Environment files. Restrict file permissions on production.
  - Rollout/Flags
    - `pip install -r requirements.txt` to install `python-dotenv`.
    - Place `.env` at project root (e.g., `/opt/vossieparent/.env` in production) and restart the service.
  - Links
    - N/A

- [2025-10-27] SendGrid email integration and admin error emails
  - Files changed
    - `config/settings.py`
  - Behavior impact
    - When `SENDGRID_API_KEY` is set, emails are sent via SendGrid using Anymail. In development without the key, emails go to the console backend.
    - Server errors email `ADMINS` using `SERVER_EMAIL` as the sender via Django's `AdminEmailHandler`.
  - Data model
    - No changes.
  - Jobs/Integrations
    - Uses `django-anymail` for ESP abstraction; SendGrid webhooks are exposed at `/webhooks/email/sendgrid/` (already included via `anymail.urls`).
  - Emails/Templates
    - `DEFAULT_FROM_EMAIL` and `SERVER_EMAIL` are read from environment variables.
  - Security/Privacy
    - Secrets are pulled from environment (`SENDGRID_API_KEY`); ensure API keys are not committed.
  - Rollout/Flags
    - Set env vars: `SENDGRID_API_KEY`, `DEFAULT_FROM_EMAIL`, `SERVER_EMAIL`, `ADMIN_EMAILS`, `ADMIN_NAME`.
    - Optional: configure SendGrid Event Webhook to POST to `${SITE_URL}/webhooks/email/sendgrid/` for delivery/bounce/complaint tracking.
  - Links
    - N/A

- [2025-10-23] Deployment script (server automation)
  - Files changed
    - `deploy.sh`
  - Behavior impact
    - No spec impact. Deploy automation only (pull from Git, install deps, migrate, collectstatic, restart service, health-check).
  - Data model
    - No changes.
  - Security/Privacy
    - Uses `systemctl` to manage the Gunicorn service; no change to app security.
  - Rollout/Flags
    - Copy to server and run with sudo. Configure variables at top (paths, service name, URLs). Ensure `STATIC_ROOT` is set in `config/settings.py` for collectstatic.

- [2025-10-23] Add .gitignore for Django/Python
  - Files changed
    - `.gitignore`
  - Behavior impact
    - No spec impact. Prevents committing local env files, caches, compiled bytecode, media uploads, collected static assets, and SQLite DB files.
  - Data model
    - No changes.
  - Jobs/Integrations
    - No changes.
  - Emails/Templates
    - No changes.
  - Security/Privacy
    - Reduces risk of committing secrets (e.g., `.env`) and sensitive local files.
  - Rollout/Flags
    - If `db.sqlite3` is tracked, run: `git rm --cached db.sqlite3` then commit to stop tracking.
  - Links
    - N/A

- [2025-10-23] Auth UI templates and login styling
  - Files changed
    - `templates/base.html`, `static/css/app.css`
    - `accounts/views.py`
    - `templates/account/login.html`, `templates/account/signup.html`, `templates/account/logout.html`
    - `templates/account/password_reset.html`, `templates/account/password_reset_done.html`
    - `templates/account/password_reset_from_key.html`, `templates/account/password_reset_from_key_done.html`
    - `templates/account/verification_sent.html`, `templates/account/email_confirm.html`
  - Behavior impact
    - Unauthenticated pages render without the sidebar; header shows Login/Register (or Logout when authenticated).
    - Login screen centered in an elevated card with improved form styling and inline error/message display.
    - Allauth pages (signup, logout, password reset flow, email verification) now use the site layout and styling.
  - Data model
    - No changes.
  - Security/Privacy
    - No changes to auth logic; UI only. Email verification remains mandatory.
  - Rollout/Flags
    - Run `collectstatic` after deploy to publish updated CSS and templates.
    - Ensure `SITE_URL` and `ALLOWED_HOSTS` are set for production.

- [2025-10-23] Notices, UI scaffolding, and email digest
  - Files changed
    - `content/models.py`, `content/admin.py`, `content/services.py`, `content/views.py`, `content/urls.py`
    - `jobs/tasks.py`, `static/css/app.css`
    - `templates/content/announcements.html`, `templates/content/announcement_detail.html`, `templates/content/documents.html`
    - `templates/emails/notices_digest.html`, `templates/emails/notices_digest.txt`
    - `templates/base.html`, `templates/home.html`
    - `config/settings.py` (static files, app registration), `config/urls.py`
  - Behavior impact
    - Announcements page shows 4 buckets: Personal, Student, Module, General. Read receipts recorded on view.
    - Home page renders a dashboard layout with sidebar navigation and quick links.
    - Email digest includes the same 4 buckets with absolute links back to the portal and unsubscribe.
  - Data model
    - `Announcement` extended with `severity`, `audience`, `to_user`, `student`, `module`, `created_by`.
    - `ReadReceipt` unchanged (tracks read state per user/announcement).
  - Jobs
    - `jobs/tasks.py::send_parent_update` now injects `notices` (7-day window) and `subject_vars` into campaign context, capped to 5 per bucket.
  - Emails/templates
    - Add `EmailTemplate` in admin for digest with:
      - `subject_template`: `Your Eduvos notices ({total})`
      - `html_template_path`: `emails/notices_digest.html`
      - `text_template_path`: `emails/notices_digest.txt`
    - Create a `Campaign` pointing to this template and schedule weekly (e.g., `0 7 * * MON`).
  - Security/Privacy
    - Detail view permission checks per audience; read receipts created only for authorized users.
  - Rollout/Flags
    - Migrate DB, register EmailTemplate + Campaign, author sample announcements in admin.

- [2025-10-23] Sponsor 1 Email (edv_sponsoremail1) lookup helper
- Files: `crm/service.py`
- Behavior impact: Internal helpers to verify whether a parent email appears as Sponsor 1 Email on Dataverse `contacts`. Enables login flows or admin checks to gate access based on sponsor linkage if required.
- Data model: No changes.
- Integrations/Jobs: Uses Dataverse Web API filter on `contacts` by `edv_sponsoremail1`. No jobs added.
- Emails/Templates: None.
- Security/Privacy: Server-to-server OAuth via MSAL using existing app credentials. No additional scopes beyond `DYNAMICS_ORG_URL/.default`.
- Rollout/Flags: Set `DYN_ORG_URL` to `https://eduvosce.crm4.dynamics.com`. Ensure the app registration has API permissions for Dataverse and that `edv_sponsoremail1` is readable for the application user.
- Links: N/A

- [2025-10-23] Deployment: auto-stash and ignore collected static
  - Files changed
    - `deploy.sh`, `.gitignore`
  - Behavior impact
    - `deploy.sh` now stashes local changes (including untracked like .pyc) before pulling to avoid merge failures.
    - Git now ignores `static_build/` (collectstatic output) to keep build artifacts out of version control.
  - Data model
    - No changes.
  - Integrations/Jobs
    - No changes.
  - Emails/Templates
    - No changes.
  - Security/Privacy
    - No changes.
  - Rollout/Flags
    - On existing clones, run: `git ls-files -ci --exclude-standard -z | xargs -0 git rm -r --cached --` then `git rm -r --cached static_build || true` and commit to stop tracking ignored files.
  - Links
    - N/A

- [2025-10-26] Allauth username-less signup config fix
  - Files changed
    - `config/settings.py`
  - Behavior impact
    - Fixes signup error: “User has no field named 'username'” when using custom user with `username=None`. Signup/login now use email-only.
  - Data model
    - No changes.
  - Jobs/Integrations
    - No changes.
  - Emails/Templates
    - No changes.
    - No changes.
  - Rollout/Flags
    - Deploy and restart app service. Ensure allauth version supports `ACCOUNT_USER_MODEL_USERNAME_FIELD=None` and `ACCOUNT_USERNAME_REQUIRED=False`.
  - Links
    - N/A

- [2025-10-28] Dev: static file serving fix
  - Files changed
    - `config/settings.py`
  - Behavior impact
    - No spec impact. Local development now serves static assets reliably (DEBUG parsing tolerant of True/1/etc.; STATIC_URL absolute).
  - Data model
    - No changes.
  - Jobs/Integrations
    - No changes.
  - Emails/Templates
    - No changes.
  - Security/Privacy
    - No changes.
  - Rollout/Flags
    - Set `DEBUG=1` (or `True`) in `.env`; restart dev server to apply.

- [2025-10-28] Dev: Auto-verify email on localhost
  - Files changed
    - `config/settings.py`, `accounts/adapter.py`, `accounts/signals.py`
  - Behavior impact
    - When `SITE_URL` starts with `http://localhost:8000`, allauth email verification is disabled and the user's primary `EmailAddress` is marked verified on login. Signup/login flows no longer require email confirmation locally. No effect in non-local environments.
  - Data model
    - No changes.
  - Integrations/Jobs
    - No changes.
  - Emails/Templates
    - No changes.
  - Security/Privacy
    - Dev-only safeguard via `SITE_URL` check. Ensure `SITE_URL` is never set to localhost in staging/production.
  - Rollout/Flags
    - For local dev, set `SITE_URL=http://localhost:8000` in `.env` and restart server.
  - Links
    - N/A

- [2025-10-28] Security hardening + Allauth/Axes deprecations + SendGrid webhook verification
  - Files changed
    - `config/settings.py`
  - Behavior impact
    - Removes allauth deprecated settings in favor of `ACCOUNT_LOGIN_METHODS` and `ACCOUNT_SIGNUP_FIELDS`.
    - Adds env-driven security toggles: `SECURE_SSL_REDIRECT`, HSTS (`SECURE_HSTS_SECONDS`, include-subdomains, preload), `SECURE_PROXY_SSL_HEADER` via `USE_X_FORWARDED_PROTO`.
    - Parses `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` from env; production links/emails should reflect `SITE_URL`.
    - Configures Anymail SendGrid tracking webhook signature verification via `SENDGRID_TRACKING_WEBHOOK_VERIFICATION_KEY`.
    - Replaces deprecated `AXES_LOCK_OUT_BY_USER_OR_IP` with `AXES_LOCKOUT_PARAMETERS`.
  - Data model
    - No changes.
  - Integrations/Jobs
    - SendGrid Event Webhook must be pointed to `/webhooks/email/sendgrid/tracking/` and have "Signed Events" enabled. Set env `SENDGRID_TRACKING_WEBHOOK_VERIFICATION_KEY` to the Base64 public key from SendGrid.
  - Emails/Templates
    - No changes.
  - Security/Privacy
    - Enables HTTPS enforcement/HSTS when env flags are set; encourages strong `SECRET_KEY` from env; verifies SendGrid webhook signatures.
  - Rollout/Flags
    - On production `.env`, set:
      - `DEBUG=0`
      - `ALLOWED_HOSTS=<your_domain>,localhost`
      - `CSRF_TRUSTED_ORIGINS=https://<your_domain>`
      - `SITE_URL=https://<your_domain>`
      - `SECURE_SSL_REDIRECT=1`, `SECURE_HSTS_SECONDS=31536000`, `SECURE_HSTS_INCLUDE_SUBDOMAINS=1`, `SECURE_HSTS_PRELOAD=1`
      - `USE_X_FORWARDED_PROTO=1` (if behind TLS-terminating proxy)
      - `SECRET_KEY=<strong_random_64+ chars>`
      - `SENDGRID_API_KEY=<existing>` and `SENDGRID_TRACKING_WEBHOOK_VERIFICATION_KEY=<from SendGrid>`
    - Redeploy and verify `/accounts/login/` and webhook health.

- [2025-11-10] Legal: Terms of Service and Privacy pages
  - Files changed
    - `content/views.py`, `content/urls.py`, `templates/base.html`, `templates/content/terms.html`, `templates/content/privacy.html`
  - Behavior impact
    - Adds two public pages: Terms of Service (`/terms/`) and Privacy Policy (`/privacy/`). Footer now includes links to both pages on all views.
  - Data model
    - No changes. (migration: no)
  - Integrations/Jobs
    - No changes.
  - Emails/Templates
    - New templates: `templates/content/terms.html`, `templates/content/privacy.html`.
  - Security/Privacy
    - Improves transparency by surfacing privacy policy; pages are publicly accessible without authentication.
  - Rollout/Flags
    - No flags. Deploy and verify that `/terms/` and `/privacy/` load and footer links are visible.
  - Links
    - N/A

- [2025-11-10] UI: Header and footer layout polish (no spec impact)
  - Files changed
    - `templates/base.html`, `static/css/app.css`
  - Behavior impact
    - Brand now links to home; a Home button is shown next to Logout when authenticated.
    - Sticky header with subtle shadow; footer spacing and visibility improved; responsive tweaks (hide search on narrow screens).
  - Data model
    - No changes. (migration: no)
  - Integrations/Jobs
    - No changes.
  - Emails/Templates
    - No changes.
  - Security/Privacy
    - No changes.
  - Rollout/Flags
    - No flags. Clear static cache if needed and reload.
  - Links
    - N/A

- [2025-11-10] Students: Load CRM contact details on list page (demo)
  - Files changed
    - `crm/service.py`, `students/views.py`, `templates/students/list.html`
  - Behavior impact
    - The Students page fetches and displays basic details for contact `16b7f729-473c-ee11-bdf4-000d3adf7716` from Dynamics as a demo block (fullname, first/last, email, sponsor email 1, contact id).
  - Data model
    - No changes. (migration: no)
  - Integrations/Jobs
    - Uses existing MSAL/Dynamics client (`dyn_get`). If `DYNAMICS_ORG_URL` is unset or the request fails, the page still loads and omits the block.
  - Emails/Templates
    - No changes.
  - Security/Privacy
    - No sensitive data persisted; read-only call. Ensure proper permissions on the Dynamics app registration.
  - Rollout/Flags
    - No flags. To disable, remove the block in `students/views.py` and template.
  - Links
    - N/A