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
from crm.msal_client import DynamicsAuthError, dyn_get, get_app_token
import requests
import base64
import json
import os

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
        self.stdout.write(f"Org URL: {settings.DYNAMICS_ORG_URL or '(unset)'}")
        self.stdout.write(
            "Tenant: "
            + (settings.DYNAMICS_TENANT_ID[:6] + "…" if settings.DYNAMICS_TENANT_ID else "(unset)")
            + " | ClientId: "
            + (settings.DYNAMICS_CLIENT_ID[:6] + "…" if settings.DYNAMICS_CLIENT_ID else "(unset)")
        )
        # Config checks
        missing = []
        mapping = {
            "DYN_TENANT_ID": "DYNAMICS_TENANT_ID",
            "DYN_CLIENT_ID": "DYNAMICS_CLIENT_ID",
            "DYN_CLIENT_SECRET": "DYNAMICS_CLIENT_SECRET",
            "DYN_ORG_URL": "DYNAMICS_ORG_URL",
        }
        for n in ["DYN_TENANT_ID", "DYN_CLIENT_ID", "DYN_CLIENT_SECRET", "DYN_ORG_URL"]:
            if not getattr(settings, mapping[n], None):
                missing.append(n)
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

        # Token claims (helps catch tenant/audience mismatches)
        try:
            token = get_app_token()
            hdr_b64, payload_b64, _sig = token.split(".")
            def _b64url_decode(s: str):
                s += "=" * (-len(s) % 4)
                return base64.urlsafe_b64decode(s.encode("utf-8"))
            # header = json.loads(_b64url_decode(hdr_b64))  # not currently used
            payload = json.loads(_b64url_decode(payload_b64))
            aud = payload.get("aud")
            tid = payload.get("tid")
            appid = payload.get("appid") or payload.get("azp")
            roles = payload.get("roles")
            self.stdout.write("Token claims:")
            self.stdout.write(f"  aud: {aud}")
            self.stdout.write(f"  tid: {tid}")
            self.stdout.write(f"  appid/azp: {appid}")
            if roles:
                self.stdout.write(f"  roles: {', '.join(roles)}")
        except DynamicsAuthError as e:
            self.stdout.write(self.style.ERROR(f"Token acquisition error: {e}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Token decode error: {e}"))

        # WhoAmI probe to confirm app user identity and BU
        try:
            self.stdout.write("Probing WhoAmI()...")
            who = dyn_get("WhoAmI")
            user_id = who.get("UserId")
            bu_id = who.get("BusinessUnitId")
            self.stdout.write(f"WhoAmI: UserId={user_id} BU={bu_id}")
            if user_id:
                # Fetch systemuser details and BU name
                usr = dyn_get(
                    f"systemusers({user_id})",
                    params={
                        "$select": "fullname,domainname,azureactivedirectoryobjectid",
                        "$expand": "businessunitid($select=name)",
                    },
                    include_annotations=True,
                )
                self.stdout.write("Application User details:")
                self.stdout.write(f"  fullname: {usr.get('fullname')}")
                self.stdout.write(f"  domainname: {usr.get('domainname')}")
                self.stdout.write(
                    f"  aad object id: {usr.get('azureactivedirectoryobjectid')}"
                )
                bu = usr.get("businessunitid") or {}
                bu_name = None
                if isinstance(bu, dict):
                    bu_name = bu.get("name") or bu.get(
                        "businessunitid@OData.Community.Display.V1.FormattedValue"
                    )
                self.stdout.write(f"  business unit: {bu_name or bu_id}")
                # List assigned role names
                try:
                    roles = dyn_get(
                        f"systemusers({user_id})/systemuserroles_association",
                        params={"$select": "name,roleid", "$top": "50"},
                    )
                    names = [r.get("name") for r in roles.get("value", [])]
                    self.stdout.write("Assigned roles (top 50):")
                    for n in names:
                        self.stdout.write(f"  - {n}")
                    if not names:
                        self.stdout.write("  (none)")
                except requests.HTTPError as e:
                    status = getattr(e.response, "status_code", "?")
                    self.stdout.write(self.style.WARNING(f"Unable to list roles (HTTP {status})"))
        except DynamicsAuthError as e:
            self.stdout.write(self.style.ERROR(f"WhoAmI auth error: {e}"))
        except requests.HTTPError as e:
            status = getattr(e.response, "status_code", "?")
            body = getattr(e.response, "text", "")[:300]
            self.stdout.write(self.style.ERROR(f"WhoAmI HTTP {status}: {body}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"WhoAmI unexpected error: {e}"))

        # Minimal access probes for key tables
        try:
            self.stdout.write("Probing Contacts read (top 1)...")
            probe_contacts = dyn_get(
                "contacts",
                params={"$select": "contactid", "$top": "1"},
            )
            count = len(probe_contacts.get("value", []))
            self.stdout.write(self.style.SUCCESS(f"Contacts read OK (got {count})"))
        except requests.HTTPError as e:
            status = getattr(e.response, "status_code", "?")
            body = getattr(e.response, "text", "")[:200]
            self.stdout.write(self.style.ERROR(f"Contacts read HTTP {status}: {body}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Contacts probe error: {e}"))

        try:
            link_table = (
                os.environ.get("DYN_PARENT_STUDENT_LINK_TABLE")
                or getattr(settings, "DYNAMICS_PARENT_STUDENT_LINK_TABLE", "")
                or "new_parentstudentlinks"
            )
            self.stdout.write(
                f"Probing {link_table} read (top 1)..."
            )
            probe_links = dyn_get(
                link_table,
                params={"$select": "_studentid_value", "$top": "1"},
            )
            count = len(probe_links.get("value", []))
            self.stdout.write(self.style.SUCCESS(f"Link table read OK (got {count})"))
        except requests.HTTPError as e:
            status = getattr(e.response, "status_code", "?")
            body = getattr(e.response, "text", "")[:200]
            self.stdout.write(self.style.ERROR(f"Link table read HTTP {status}: {body}"))
            if status == 404:
                self.stdout.write(
                    self.style.WARNING(
                        "Hint: Set DYN_PARENT_STUDENT_LINK_TABLE to the correct entity set logical name for the parent-student link table."
                    )
                )
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Link table probe error: {e}"))
        # Attempt fetch
        try:
            if use_raw:
                self.stdout.write("Using raw dyn_get...")
                res = dyn_get(
                    f"contacts({cid})",
                    params={
                        "$select": (
                            "contactid,firstname,lastname,fullname,emailaddress1"
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