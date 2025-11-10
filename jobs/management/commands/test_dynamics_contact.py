"""Management command to diagnose Dynamics contact retrieval.

Usage:
    python manage.py test_dynamics_contact --id <contact-guid>

Reports configuration status, attempts a fetch using get_contact_by_id,
and surfaces HTTP/permission errors. Exits with non-zero status if
the contact cannot be retrieved.
"""
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from crm.service import get_contact_by_id
from crm.msal_client import DynamicsAuthError, dyn_get
import requests

DEFAULT_CONTACT_ID = "16b7f729-473c-ee11-bdf4-000d3adf7716"


class Command(BaseCommand):
    help = "Diagnose Dynamics / Dataverse contact retrieval by id"

    def add_arguments(self, parser):
        parser.add_argument(
            "--id",
            dest="contact_id",
            default=DEFAULT_CONTACT_ID,
            help="Contact GUID to fetch (default demo id)",
        )
        parser.add_argument(
            "--raw",
            action="store_true",
            help="Use raw dyn_get instead of helper (shows low-level errors)",
        )

    def handle(self, *args, **options):
        cid = options["contact_id"].strip()
        use_raw = options["raw"]
        self.stdout.write("== Dynamics Contact Diagnostics ==")
        self.stdout.write(f"Contact ID: {cid}")
        # Config checks
        missing = [
            n
            for n in [
                "DYN_TENANT_ID",
                "DYN_CLIENT_ID",
                "DYN_CLIENT_SECRET",
                "DYN_ORG_URL",
            ]
            if not settings.__dict__.get(
                {
                    "DYN_TENANT_ID": "DYNAMICS_TENANT_ID",
                    "DYN_CLIENT_ID": "DYNAMICS_CLIENT_ID",
                    "DYN_CLIENT_SECRET": "DYNAMICS_CLIENT_SECRET",
                    "DYN_ORG_URL": "DYNAMICS_ORG_URL",
                }[n]
            )
        ]
        if missing:
            self.stdout.write(
                self.style.ERROR(
                    "Missing required environment variables: " + ", ".join(missing)
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS("All required Dynamics env vars set."))
        if not settings.DYNAMICS_SCOPE:
            self.stdout.write(self.style.ERROR("Dynamics scope is empty (DYN_ORG_URL unset?)"))
        # Attempt fetch
        try:
            if use_raw:
                self.stdout.write("Using raw dyn_get...")
                res = dyn_get(
                    f"contacts({cid})",
                    params={
                        "$select": (
                            "contactid,firstname,lastname,fullname,emailaddress1,edv_sponsoremail1"
                        )
                    },
                    include_annotations=True,
                )
            else:
                self.stdout.write("Using helper get_contact_by_id()...")
                res = get_contact_by_id(cid)
            if not res:
                raise CommandError("Contact not found or empty response")
        except DynamicsAuthError as e:
            raise CommandError(f"Auth error acquiring token: {e}")
        except requests.HTTPError as e:  # surface HTTP details
            status = getattr(e.response, "status_code", "?")
            body = getattr(e.response, "text", "")[:500]
            raise CommandError(f"HTTP {status} error: {body}")
        except Exception as e:
            raise CommandError(f"Unhandled error: {e}")

        # Success output
        self.stdout.write(self.style.SUCCESS("Contact retrieved successfully."))
        for field in [
            "contactid",
            "fullname",
            "firstname",
            "lastname",
            "emailaddress1",
            "edv_sponsoremail1",
        ]:
            self.stdout.write(f"  {field}: {res.get(field)}")
        annotations = [
            k for k in res.keys() if "@OData.Community.Display.V1.FormattedValue" in k
        ]
        if annotations:
            self.stdout.write("Formatted value annotations present (truncated):")
            for k in annotations[:10]:
                self.stdout.write(f"  {k}: {res.get(k)}")
        self.stdout.write("== Done ==")