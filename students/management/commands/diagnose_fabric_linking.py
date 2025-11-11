from django.core.management.base import BaseCommand
from django.conf import settings
from accounts.models import User
from allauth.account.models import EmailAddress
from students.fabric import (
    fetch_contacts_by_sponsor_email,
    _pyodbc_query,
)


class Command(BaseCommand):
    help = (
        "Diagnose Fabric sponsor-email linking for a user. "
        "Shows which emails are tested and matching students."
    )

    def add_arguments(self, parser):
        parser.add_argument("--user-id", type=int, help="User id")
        parser.add_argument("--email", type=str, help="User email")
        parser.add_argument(
            "--include-unverified",
            action="store_true",
            help="Include unverified alternates",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Apply links (run validate_parent_via_fabric)",
        )
        parser.add_argument(
            "--limit", type=int, default=100, help="Max matches per email"
        )
        parser.add_argument(
            "--scan",
            action="store_true",
            help=(
                "Scan INFORMATION_SCHEMA for columns likely to contain "
                "sponsor email addresses and list candidate tables"
            ),
        )

    def handle(self, *args, **opts):
        if "fabric" not in settings.DATABASES:
            self.stderr.write("Fabric DB not configured (settings.DATABASES).")
            return

        # Optional schema scan
        if opts.get("scan"):
            self._scan_columns()
            return

        user = None
        if opts.get("user_id"):
            user = User.objects.filter(id=opts["user_id"]).first()
        elif opts.get("email"):
            user = User.objects.filter(email__iexact=opts["email"]).first()
        if not user:
            self.stderr.write("User not found. Use --user-id or --email.")
            return

        inc_unverified = (
            opts.get("include_unverified")
            or getattr(
                settings,
                "FABRIC_INCLUDE_UNVERIFIED_ALT_EMAILS",
                False,
            )
        )
        self.stdout.write(
            f"User: id={user.id} email={user.email} include_unverified="
            f"{bool(inc_unverified)}"
        )

        emails = set()
        if user.email:
            emails.add(user.email.strip().lower())
        q = EmailAddress.objects.filter(user=user)
        if not inc_unverified:
            q = q.filter(verified=True)
        for ea in q.only("email"):
            if ea.email:
                emails.add(ea.email.strip().lower())

        self.stdout.write(
            f"Emails considered ({len(emails)}):\n  - "
            + "\n  - ".join(sorted(emails))
        )

        total = 0
        for e in sorted(emails):
            rows = fetch_contacts_by_sponsor_email(e, limit=opts["limit"])
            total += len(rows)
            self.stdout.write(
                f"\nEmail {e}: {len(rows)} match(es)"
            )
            for r in rows[:10]:
                s1 = r.get("btfh_sponsor1email")
                s2 = r.get("btfh_sponsor2email")
                self.stdout.write(
                    "  - contactid=%s name=%s %s s1=%s s2=%s"
                    % (
                        r.get("contactid"),
                        r.get("firstname") or "",
                        r.get("lastname") or "",
                        str(s1),
                        str(s2),
                    )
                )

    def _scan_columns(self):
        self.stdout.write("Scanning for candidate sponsor/email columns...")
        q = (
            "SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME"
            " FROM INFORMATION_SCHEMA.COLUMNS"
            " WHERE (LOWER(COLUMN_NAME) LIKE '%sponsor%'"
            "        OR LOWER(COLUMN_NAME) LIKE '%guardian%')"
            "   AND LOWER(COLUMN_NAME) LIKE '%email%'"
            " ORDER BY 1,2,3"
        )
        rows = _pyodbc_query(q, [])
        if not rows:
            self.stdout.write("No candidate columns found.")
            return
        current = None
        count = 0
        for r in rows:
            key = (r.get("TABLE_SCHEMA"), r.get("TABLE_NAME"))
            if key != current:
                if current is not None:
                    self.stdout.write("")
                self.stdout.write(
                    f"Table: {key[0]}.{key[1]}"
                )
                current = key
                count += 1
            self.stdout.write(f"  - {r.get('COLUMN_NAME')}")
        self.stdout.write(f"\nTables with candidate columns: {count}")
