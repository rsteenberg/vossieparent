import os
import pyodbc
import msal
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            dest="email",
            help="Filter by sponsor1 email",
        )
        parser.add_argument(
            "--schema",
            dest="schema",
            default="PP",
            help="Table schema (default: PP)",
        )
        parser.add_argument(
            "--table",
            dest="table",
            default="contact_v2",
            help="Table name (default: contact_v2)",
        )
        parser.add_argument(
            "--limit",
            dest="limit",
            type=int,
            default=5,
            help="Limit rows returned for the email filter query (default: 5)",
        )

    def handle(self, *args, **options):
        alias = "fabric"
        dbs = getattr(settings, "DATABASES", {})
        if alias not in dbs:
            raise CommandError(
                "DATABASES['fabric'] not configured. "
                "Set FABRIC_DB (and FABRIC_HOST) in environment."
            )

        cfg = dbs[alias]
        opts = cfg.get("OPTIONS", {})
        driver = opts.get("driver", "ODBC Driver 17 for SQL Server")
        server = cfg.get("HOST", "")
        name = cfg.get("NAME", "")
        user = cfg.get("USER", "")
        pwd = cfg.get("PASSWORD", "")
        # Build connection string similar to mssql-django
        parts = [
            f"DRIVER={{{driver}}}",
            f"SERVER={server}",
            f"DATABASE={name}",
        ]
        if user:
            parts.append(f"UID={user}")
            parts.append(f"PWD={pwd}")
        extra = opts.get("extra_params")
        connstr = ";".join(parts) + (";" + extra if extra else "")

        # Print sanitized connection string for diagnostics
        masked = connstr.replace(pwd, "***") if pwd else connstr
        self.stdout.write(f"ODBC connstr: {masked}")

        try:
            cn = pyodbc.connect(connstr, timeout=30)
        except Exception as e:
            # Fallback: try MSAL access token if Authentication attr unsupported
            err_text = str(e)
            self.stdout.write("Direct ODBC connect failed; trying token-based auth...")
            tenant = (
                getattr(settings, "DYNAMICS_TENANT_ID", "")
                or os.environ.get("AZURE_TENANT_ID", "")
            )
            if not (tenant and user and pwd):
                raise CommandError(f"ODBC connect failed: {err_text}")

            authority = f"https://login.microsoftonline.com/{tenant}"
            app = msal.ConfidentialClientApplication(
                client_id=user, client_credential=pwd, authority=authority
            )
            result = app.acquire_token_for_client(
                scopes=["https://database.windows.net/.default"]
            )
            access_token = result.get("access_token")
            if not access_token:
                raise CommandError(
                    "Token acquisition failed for SQL scope; cannot fallback"
                )

            def _prepare_token(tok: str) -> bytes:
                tbytes = tok.encode()
                exptoken = b""  # interleave null bytes
                for b in tbytes:
                    exptoken += bytes({b})
                    exptoken += bytes(1)
                import struct

                return struct.pack("=i", len(exptoken)) + exptoken

            token_attr_key = 1256  # SQL_COPT_SS_ACCESS_TOKEN
            token_bytes = _prepare_token(access_token)
            # Build minimal connstr without UID/PWD or Authentication
            token_conn = ";".join(
                [
                    f"DRIVER={{{driver}}}",
                    f"SERVER={server}",
                    f"DATABASE={name}",
                    "Encrypt=yes",
                    "TrustServerCertificate=no",
                ]
            )
            self.stdout.write("ODBC token-connstr (sanitized): " + token_conn)
            cn = pyodbc.connect(
                token_conn,
                attrs_before={token_attr_key: token_bytes},
                timeout=30,
            )

        try:
            cr = cn.cursor()
            # Show current DB for clarity
            cr.execute("SELECT DB_NAME()")
            dbn = cr.fetchone()[0]
            self.stdout.write(f"Connected to DB: {dbn}")

            schema = options.get("schema") or "PP"
            table = options.get("table") or "contact_v2"
            full_name = f"[{schema}].[{table}]"

            try:
                cr.execute(f"SELECT COUNT(*) FROM {full_name}")
                count_row = cr.fetchone()
                self.stdout.write(f"{schema}.{table} count: {count_row[0]}")
            except Exception as e:
                self.stdout.write(
                    f"COUNT failed for {schema}.{table}: {e}. Listing available tables..."
                )
                cr.execute(
                    "SELECT TOP 50 TABLE_SCHEMA, TABLE_NAME "
                    "FROM INFORMATION_SCHEMA.TABLES ORDER BY 1,2"
                )
                rows = cr.fetchall()
                for r in rows:
                    self.stdout.write(f"- {r[0]}.{r[1]}")
                self.stdout.write("Searching for tables containing 'contact'...")
                cr.execute(
                    "SELECT TOP 50 TABLE_SCHEMA, TABLE_NAME "
                    "FROM INFORMATION_SCHEMA.TABLES "
                    "WHERE LOWER(TABLE_NAME) LIKE '%contact%' ORDER BY 1,2"
                )
                rows = cr.fetchall()
                for r in rows:
                    self.stdout.write(f"* {r[0]}.{r[1]}")
                # Stop early if the target table isn't found
                return

            email = options.get("email")
            if email:
                limit = int(options.get("limit") or 5)
                cr.execute(
                    (
                        f"SELECT TOP {limit} * FROM {full_name} "
                        "WHERE btfh_sponsor1email = ?"
                    ),
                    [email],
                )
                rows = cr.fetchall()
                self.stdout.write(f"Rows for email {email}: {len(rows)}")
                if rows:
                    self.stdout.write(str(rows[0]))
        finally:
            try:
                cn.close()
            except Exception:
                pass
