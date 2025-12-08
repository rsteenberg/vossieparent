from django.utils import timezone
from django.conf import settings
from accounts.models import User
from students.models import Student, ParentStudentLink
from .msal_client import dyn_get
import logging
from decimal import Decimal

logger = logging.getLogger(__name__)


def validate_parent(user: User) -> bool:
    try:
        if "fabric" in settings.DATABASES:
            from students.fabric import validate_parent_via_fabric
            if validate_parent_via_fabric(user):
                return True
    except Exception as e:
        logger.warning("Fabric validation error: %s", str(e))
    if not settings.DYNAMICS_ORG_URL:
        return False
    contact = None
    if user.external_parent_id:
        try:
            contact = dyn_get(f"contacts({user.external_parent_id})")
        except Exception:
            contact = None
    if not contact:
        try:
            res = dyn_get(
                "contacts",
                params={
                    "$select": "contactid,emailaddress1,firstname,lastname",
                    "$filter": f"emailaddress1 eq '{user.email}'",
                },
            )
            values = res.get("value", [])
            contact = values[0] if values else None
        except Exception:
            contact = None
    active_students = []
    if contact:
        # No link table: find students by sponsor email field using the parent's login email
        sponsor_field = getattr(
            settings, "DYNAMICS_SPONSOR1_EMAIL_FIELD", "btfh_sponsor1email"
        )
        # Use the authenticated user's email address as the join key
        parent_email = (user.email or "").strip()
        if parent_email:
            # Case-insensitive compare using tolower() in OData
            parent_email_lower = parent_email.lower()
            safe_parent_email = parent_email_lower.replace("'", "''")
            try:
                res = dyn_get(
                    "contacts",
                    params={
                        "$select": "contactid,firstname,lastname",
                        "$filter": (
                            f"{sponsor_field} ne null and {sponsor_field} ne '' and "
                            f"tolower({sponsor_field}) eq '{safe_parent_email}'"
                        ),
                        "$top": 100,
                    },
                )
                for row in res.get("value", []):
                    external_student_id = row.get("contactid")
                    if not external_student_id:
                        continue
                    st, _ = Student.objects.get_or_create(
                        external_student_id=external_student_id,
                        defaults={"first_name": "", "last_name": ""},
                    )
                    first = row.get("firstname") or ""
                    last = row.get("lastname") or ""
                    if (
                        (first and st.first_name != first)
                        or (last and st.last_name != last)
                    ):
                        st.first_name = first
                        st.last_name = last
                        st.save(update_fields=["first_name", "last_name"])
                    ParentStudentLink.objects.update_or_create(
                        user=user,
                        student=st,
                        defaults={
                            "active": True,
                            "last_verified_at": timezone.now(),
                        },
                    )
                    active_students.append(st.id)
            except Exception:
                pass
    if not active_students:
        contacts = get_contacts_by_sponsor1_email(user.email)
        for c in contacts:
            sid = c.get("contactid")
            if not sid:
                continue
            st, _ = Student.objects.get_or_create(
                external_student_id=sid,
                defaults={"first_name": "", "last_name": ""},
            )
            first = c.get("firstname") or ""
            last = c.get("lastname") or ""
            if (
                (first and st.first_name != first)
                or (last and st.last_name != last)
            ):
                st.first_name = first
                st.last_name = last
                st.save(update_fields=["first_name", "last_name"])
            ParentStudentLink.objects.update_or_create(
                user=user,
                student=st,
                defaults={"active": True, "last_verified_at": timezone.now()},
            )
            active_students.append(st.id)
    if active_students:
        ParentStudentLink.objects.filter(user=user).exclude(
            student_id__in=active_students
        ).update(active=False)
        update_fields = ["last_validated_at"]
        if (
            contact
            and contact.get("contactid")
            and user.external_parent_id != contact["contactid"]
        ):
            user.external_parent_id = contact["contactid"]
            update_fields.append("external_parent_id")
        user.last_validated_at = timezone.now()
        user.save(update_fields=update_fields)
    return bool(active_students)


def get_contacts_by_sponsor1_email(email):
    if not email:
        return []
    
    # Check local Contact table first
    try:
        from crm.models import Contact
        qs = Contact.objects.filter(sponsor1_email__iexact=email.strip())
        if qs.exists():
            return [c.raw_data for c in qs]
    except Exception:
        pass

    if not settings.DYNAMICS_ORG_URL:
        return []
        
    sponsor_field = getattr(
        settings, "DYNAMICS_SPONSOR1_EMAIL_FIELD", "btfh_sponsor1email"
    )
    # Case-insensitive compare using tolower() in OData
    safe_email = (email or "").strip().lower().replace("'", "''")
    try:
        res = dyn_get(
            "contacts",
            params={
                "$select": (
                    "contactid,firstname,lastname,fullname,"
                    "emailaddress1"
                ),
                "$filter": (
                    f"{sponsor_field} ne null and {sponsor_field} ne '' and "
                    f"tolower({sponsor_field}) eq '{safe_email}'"
                ),
            },
        )
        return res.get("value", [])
    except Exception:
        return []


def is_user_sponsor1_email(user: User) -> bool:
    return bool(get_contacts_by_sponsor1_email(user.email))


def get_contact_by_id(contact_id: str):
    """Fetch a single Dataverse contact by id.

    Returns dict or None. Selects commonly needed fields.
    Gracefully returns None if Dynamics isn't configured or call fails.
    Adds debug logging for failure cases to aid troubleshooting.
    """
    from django.conf import settings

    if not contact_id:
        logger.debug("get_contact_by_id skipped: empty contact_id")
        return None

    # Check local Contact table first
    try:
        from crm.models import Contact
        c = Contact.objects.filter(contact_id=contact_id).first()
        if c:
            return c.raw_data
    except Exception:
        pass

    if not settings.DYNAMICS_ORG_URL:
        logger.debug("get_contact_by_id skipped: DYNAMICS_ORG_URL not set")
        return None
    try:
        contact = dyn_get(
            f"contacts({contact_id})",
            params={
                "$select": (
                    "contactid,firstname,lastname,fullname,"  # names
                    "emailaddress1"  # built-in email field only (custom optional)
                )
            },
            include_annotations=True,
        )
        if not contact:
            logger.info("Dynamics contact %s returned empty payload", contact_id)
        return contact or None
    except Exception as e:
        logger.warning(
            "Failed to fetch Dynamics contact %s: %s", contact_id, str(e)
        )
        return None


def get_contact_balance(contact_id: str):
    if not contact_id:
        return None
    try:
        if "fabric" in settings.DATABASES:
            from students.fabric import fetch_contact_by_id as fabric_contact_by_id

            row = fabric_contact_by_id(contact_id)
            if row and "bt_collectionbalance" in row:
                v = row.get("bt_collectionbalance")
                try:
                    amt = Decimal(str(v)) if v is not None else None
                except Exception:
                    amt = None
                if amt is not None:
                    return {"amount": amt, "formatted": f"R {amt:,.2f}"}
    except Exception as e:
        logger.warning("Fabric balance fetch failed for %s: %s", contact_id, str(e))

    if not settings.DYNAMICS_ORG_URL:
        return None
    try:
        res = dyn_get(
            f"contacts({contact_id})",
            params={"$select": "bt_collectionbalance"},
            include_annotations=True,
        )
        if not res:
            return None
        v = res.get("bt_collectionbalance")
        fv = res.get(
            "bt_collectionbalance@OData.Community.Display.V1.FormattedValue"
        )
        amt = None
        if v is not None:
            try:
                amt = Decimal(str(v))
            except Exception:
                amt = None
        if amt is not None:
            label = fv or f"R {amt:,.2f}"
            return {"amount": amt, "formatted": label}
        if fv:
            return {"amount": None, "formatted": fv}
    except Exception as e:
        logger.warning("Dynamics balance fetch failed for %s: %s", contact_id, str(e))
    return None


# Cached map of entity logical names -> entity set names
_entity_set_cache = {}


def get_entity_set_name(logical_name: str):
    if not logical_name:
        return None
    if logical_name in _entity_set_cache:
        return _entity_set_cache[logical_name]
    try:
        res = dyn_get(
            f"EntityDefinitions(LogicalName='{logical_name}')",
            params={"$select": "EntitySetName"},
        )
        name = res.get("EntitySetName")
        if name:
            _entity_set_cache[logical_name] = name
        return name
    except Exception as e:
        logger.warning("EntitySetName resolve failed for %s: %s", logical_name, str(e))
        return None


def fetchxml(logical_name: str, fetch_xml: str, include_annotations: bool = True):
    if not settings.DYNAMICS_ORG_URL:
        return {"value": []}
    esn = get_entity_set_name(logical_name) or logical_name
    try:
        return dyn_get(esn, params={"fetchXml": fetch_xml}, include_annotations=include_annotations)
    except Exception as e:
        logger.warning("FetchXML call failed for %s: %s", logical_name, str(e))
        return {"value": []}
