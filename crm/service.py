from django.utils import timezone
from django.conf import settings
from accounts.models import User
from students.models import Student, ParentStudentLink
from .msal_client import dyn_get


def validate_parent(user: User) -> bool:
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
        try:
            links = dyn_get(
                "new_parentstudentlinks",
                params={
                    "$filter": (
                        f"_parentid_value eq {contact['contactid']} "
                        "and statecode eq 0"
                    ),
                },
            )
        except Exception:
            links = {"value": []}
        for row in links.get("value", []):
            external_student_id = row.get("_studentid_value")
            if not external_student_id:
                continue
            st, _ = Student.objects.get_or_create(
                external_student_id=external_student_id,
                defaults={"first_name": "", "last_name": ""},
            )
            try:
                stu = dyn_get(
                    f"contacts({external_student_id})",
                    params={"$select": "contactid,firstname,lastname"},
                )
                first = stu.get("firstname") or ""
                last = stu.get("lastname") or ""
                if (
                    (first and st.first_name != first)
                    or (last and st.last_name != last)
                ):
                    st.first_name = first
                    st.last_name = last
                    st.save(update_fields=["first_name", "last_name"])
            except Exception:
                pass
            ParentStudentLink.objects.update_or_create(
                user=user,
                student=st,
                defaults={"active": True, "last_verified_at": timezone.now()},
            )
            active_students.append(st.id)
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
    if not settings.DYNAMICS_ORG_URL or not email:
        return []
    safe_email = email.replace("'", "''")
    try:
        res = dyn_get(
            "contacts",
            params={
                "$select": (
                    "contactid,firstname,lastname,fullname,"
                    "emailaddress1,edv_sponsoremail1"
                ),
                "$filter": f"edv_sponsoremail1 eq '{safe_email}'",
            },
        )
        return res.get("value", [])
    except Exception:
        return []


def is_user_sponsor1_email(user: User) -> bool:
    return bool(get_contacts_by_sponsor1_email(user.email))
