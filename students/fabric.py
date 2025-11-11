from django.db import connections
from django.utils import timezone
from django.conf import settings
from allauth.account.models import EmailAddress
import logging
import pyodbc
import msal

logger = logging.getLogger(__name__)


def _conn():
    return connections["fabric"]


def _row_to_dict(cursor, row):
    cols = [c[0] for c in cursor.description]
    return {cols[i]: row[i] for i in range(len(cols))}


def fetch_contact_by_id(contact_id: str):
    if not contact_id:
        return None
    try:
        for sch, tbl in _candidate_tables():
            sql = (
                f"SELECT TOP 1 * FROM [{sch}].[{tbl}] "
                "WHERE contactid = ?"
            )
            rows = _pyodbc_query(sql, [contact_id])
            if rows:
                return rows[0]
    except Exception as e:
        logger.warning(
            "Fabric pyodbc fetch_contact_by_id failed: id=%s err=%s",
            contact_id,
            str(e),
        )
    return None


essential_fields = (
    "contactid,firstname,lastname,fullname,emailaddress1,"
    "btfh_sponsor1email,btfh_sponsor2email"
)


def fetch_contacts_by_sponsor_email(email: str, limit: int = 100):
    if not email:
        return []
    e = (email or "").strip().lower()
    # Try direct pyodbc first to avoid Django DB connection attribute issues
    for sch, tbl in _candidate_tables():
        cols = _available_sponsor_columns(sch, tbl)
        if not cols:
            continue
        where = " OR ".join([f"LOWER(LTRIM(RTRIM({c}))) = ?" for c in cols])
        sql = (
            f"SELECT TOP {int(limit)} * FROM [{sch}].[{tbl}] WHERE (" f"{where})"
        )
        params = [e] * len(cols)
        result = _pyodbc_query(sql, params)
        if result:
            logger.info(
                "Fabric sponsor query (pyodbc): table=%s.%s email=%s matches=%d cols=%s",
                sch,
                tbl,
                e,
                len(result),
                ",".join(cols),
            )
            return result
    # Fallback to Django DB connection if configured
    try:
        with _conn().cursor() as cr:
            cr.execute(
                (
                    f"SELECT TOP {int(limit)} {essential_fields} "
                    "FROM [PP].[contact] WHERE ("
                    "LOWER(LTRIM(RTRIM(btfh_sponsor1email))) = ? OR "
                    "LOWER(LTRIM(RTRIM(btfh_sponsor2email))) = ?)"
                ),
                [e, e],
            )
            rows = cr.fetchall()
            result = [_row_to_dict(cr, r) for r in rows]
            logger.info(
                "Fabric sponsor query: table=PP.contact email=%s matches=%d",
                e,
                len(result),
            )
            return result
    except Exception as ex:
        logger.warning(
            "Fabric sponsor query failed on PP.contact: email=%s err=%s",
            e,
            str(ex),
        )
    logger.warning(
        "Fabric fetch by sponsor failed on all tried tables (pyodbc and Django DB): email=%s",
        e,
    )
    return []


def validate_parent_via_fabric(user) -> bool:
    emails = set()
    if getattr(user, "email", None):
        emails.add(user.email.strip().lower())
    include_unverified = bool(
        getattr(settings, "FABRIC_INCLUDE_UNVERIFIED_ALT_EMAILS", False)
    )
    q = EmailAddress.objects.filter(user=user)
    if not include_unverified:
        q = q.filter(verified=True)
    for ea in q.only("email"):
        if ea.email:
            emails.add(ea.email.strip().lower())
    logger.info(
        "Fabric validate: user_id=%s building email set",
        getattr(user, "id", "?"),
    )
    found = []
    for e in emails:
        found.extend(fetch_contacts_by_sponsor_email(e))
    logger.info(
        "Fabric validate: user_id=%s emails=%d matches=%d",
        getattr(user, "id", "?"),
        len(emails),
        len(found),
    )
    if not found:
        return False
    from students.models import Student, ParentStudentLink

    active_ids = []
    for row in found:
        sid = row.get("contactid")
        if not sid:
            continue
        st, _ = Student.objects.get_or_create(
            external_student_id=sid,
            defaults={"first_name": "", "last_name": ""},
        )
        fn = row.get("firstname") or ""
        ln = row.get("lastname") or ""
        upd = []
        if fn and st.first_name != fn:
            st.first_name = fn
            upd.append("first_name")
        if ln and st.last_name != ln:
            st.last_name = ln
            upd.append("last_name")
        if upd:
            st.save(update_fields=upd)
        ParentStudentLink.objects.update_or_create(
            user=user,
            student=st,
            defaults={"active": True, "last_verified_at": timezone.now()},
        )
        active_ids.append(st.id)
    if active_ids:
        ParentStudentLink.objects.filter(user=user).exclude(
            student_id__in=active_ids
        ).update(active=False)
        user.last_validated_at = timezone.now()
        user.save(update_fields=["last_validated_at"])
        return True
    return False


def _prepare_token(tok: str) -> bytes:
    tbytes = tok.encode()
    exptoken = b""
    for b in tbytes:
        exptoken += bytes({b})
        exptoken += bytes(1)
    import struct

    return struct.pack("=i", len(exptoken)) + exptoken


def _pyodbc_conn():
    dbs = getattr(settings, "DATABASES", {})
    cfg = dbs.get("fabric")
    if not cfg:
        logger.warning("Fabric DB config missing in settings.DATABASES")
        return None
    opts = cfg.get("OPTIONS", {})
    driver = opts.get("driver", "ODBC Driver 18 for SQL Server")
    host = cfg.get("HOST", "")
    port = str(cfg.get("PORT") or "1433")
    if host.startswith("tcp:"):
        server = host if "," in host else f"{host},{port}"
    elif "," in host:
        server = f"tcp:{host}"
    else:
        server = f"tcp:{host},{port}"
    name = cfg.get("NAME", "")
    user = cfg.get("USER") or settings.DYNAMICS_CLIENT_ID
    pwd = cfg.get("PASSWORD") or settings.DYNAMICS_CLIENT_SECRET
    tenant = getattr(settings, "DYNAMICS_TENANT_ID", "")
    if not (tenant and user and pwd and server and name):
        logger.warning("Fabric token connect missing config pieces")
        return None
    authority = f"https://login.microsoftonline.com/{tenant}"
    app = msal.ConfidentialClientApplication(
        client_id=user, client_credential=pwd, authority=authority
    )
    result = app.acquire_token_for_client(
        scopes=["https://database.windows.net/.default"]
    )
    access_token = result.get("access_token")
    if not access_token:
        logger.warning("Fabric token acquisition failed: %s", str(result))
        return None
    token_bytes = _prepare_token(access_token)
    conn_str = ";".join(
        [
            f"DRIVER={{{driver}}}",
            f"SERVER={server}",
            f"DATABASE={name}",
            "Encrypt=yes",
            "TrustServerCertificate=no",
        ]
    )
    try:
        cn = pyodbc.connect(
            conn_str,
            attrs_before={1256: token_bytes},
            timeout=30,
        )
        return cn
    except Exception as ex:
        logger.warning("Fabric pyodbc token connect failed: %s", str(ex))
        # Fallback: use service principal auth via connection string
        try:
            conn_str_sp = ";".join(
                [
                    f"DRIVER={{{driver}}}",
                    f"SERVER={server}",
                    f"DATABASE={name}",
                    "Encrypt=yes",
                    "TrustServerCertificate=no",
                    "Authentication=ActiveDirectoryServicePrincipal",
                    f"UID={user}",
                    f"PWD={pwd}",
                ]
            )
            cn2 = pyodbc.connect(conn_str_sp, timeout=30)
            return cn2
        except Exception as ex2:
            logger.warning("Fabric pyodbc SPN connect failed: %s", str(ex2))
            return None


def _pyodbc_query(sql: str, params: list):
    cn = _pyodbc_conn()
    if not cn:
        return []
    try:
        cr = cn.cursor()
        cr.execute(sql, params or [])
        rows = cr.fetchall()
        cols = [c[0] for c in cr.description]
        return [{cols[i]: r[i] for i in range(len(cols))} for r in rows]
    except Exception as ex:
        logger.warning("Fabric pyodbc query failed: %s", str(ex))
        return []
    finally:
        try:
            cn.close()
        except Exception:
            pass


def _pyodbc_columns(schema: str, table: str) -> list[str]:
    sql = (
        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?"
    )
    rows = _pyodbc_query(sql, [schema, table])
    return [r.get("COLUMN_NAME") for r in rows if r.get("COLUMN_NAME")]


def _available_sponsor_columns(schema: str, table: str) -> list[str]:
    cols = _pyodbc_columns(schema, table)
    if not cols:
        return []
    lower_map = {c.lower(): c for c in cols}
    raw = getattr(
        settings,
        "FABRIC_SPONSOR_EMAIL_FIELDS",
        "btfh_sponsor1email,btfh_sponsor2email",
    )
    cands = [c.strip() for c in raw.split(",") if c.strip()]
    avail = []
    for cand in cands:
        k = cand.lower()
        if k in lower_map:
            avail.append(lower_map[k])
    if not avail:
        # heuristic: any column containing both 'sponsor' and 'email'
        for c in cols:
            lc = c.lower()
            if "sponsor" in lc and "email" in lc:
                avail.append(c)
        # dedupe preserving order
        seen = set()
        uniq = []
        for c in avail:
            if c not in seen:
                uniq.append(c)
                seen.add(c)
        avail = uniq
    logger.info(
        "Detected sponsor-email columns on %s.%s: %s",
        schema,
        table,
        ",".join(avail) if avail else "<none>",
    )
    return avail


def _candidate_tables() -> list[tuple[str, str]]:
    raw = getattr(
        settings,
        "FABRIC_CONTACT_TABLES",
        "PP.contact",
    )
    items = [x.strip() for x in str(raw).split(",") if x.strip()]
    result = []
    for it in items:
        if "." in it:
            sch, tbl = it.split(".", 1)
            result.append((sch.strip("[]"), tbl.strip("[]")))
    return result
