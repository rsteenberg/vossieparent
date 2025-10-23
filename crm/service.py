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
        res = dyn_get(
            "contacts",
            params={
                "$select": "contactid,emailaddress1,firstname,lastname",
                "$filter": f"emailaddress1 eq '{user.email}'",
            },
        )
        values = res.get("value", [])
        contact = values[0] if values else None
    if not contact:
        return False
    links = dyn_get(
        "new_parentstudentlinks",
        params={
            "$filter": f"_parentid_value eq {contact['contactid']} and statecode eq 0",
        },
    )
    active_students = []
    for row in links.get("value", []):
        external_student_id = row.get("_studentid_value")
        if not external_student_id:
            continue
        st, _ = Student.objects.get_or_create(
            external_student_id=external_student_id
        )
        ParentStudentLink.objects.update_or_create(
            user=user,
            student=st,
            defaults={"active": True, "last_verified_at": timezone.now()},
        )
        active_students.append(st.id)
    ParentStudentLink.objects.filter(user=user).exclude(
        student_id__in=active_students
    ).update(active=False)
    user.external_parent_id = contact["contactid"]
    user.last_validated_at = timezone.now()
    user.save(update_fields=["external_parent_id", "last_validated_at"])
    return bool(active_students)


def get_contacts_by_sponsor1_email(email):
    if not settings.DYNAMICS_ORG_URL or not email:
        return []
    safe_email = email.replace("'", "''")
    res = dyn_get(
        "contacts",
        params={
            "$select": "contactid,fullname,emailaddress1,edv_sponsoremail1",
            "$filter": f"edv_sponsoremail1 eq '{safe_email}'",
        },
    )
    return res.get("value", [])


def is_user_sponsor1_email(user: User) -> bool:
    return bool(get_contacts_by_sponsor1_email(user.email))
