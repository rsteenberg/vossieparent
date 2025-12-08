from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render
from django.conf import settings
from students.models import Student
from students.permissions import parent_can_view_student
from students.fabric import fetch_atrisk_for_student, fetch_contact_by_id as fabric_contact_by_id
from crm.service import fetchxml, get_contact_by_id


@login_required
def index(request):
    sid = request.session.get("active_student_id")
    student = None
    student_number = ""
    atrisk_count = None
    if sid:
        student = Student.objects.filter(id=sid).first()
        contact = None
        if student and "fabric" in settings.DATABASES and student.external_student_id:
            try:
                contact = fabric_contact_by_id(student.external_student_id)
            except Exception:
                contact = None
        if (not contact and student and getattr(settings, "DYNAMICS_ORG_URL", "") and student.external_student_id):
            try:
                contact = get_contact_by_id(student.external_student_id)
            except Exception:
                contact = None
        if contact:
            student_number = contact.get("msdyn_contactpersonid") or ""
        if "fabric" in settings.DATABASES and student and student.external_student_id:
            try:
                rows = fetch_atrisk_for_student(student.external_student_id, limit=500)
                atrisk_count = len(rows or [])
            except Exception:
                atrisk_count = None
    ctx = {
        "active_nav": "academics",
        "active_student_id": sid,
        "active_student": student,
        "active_student_number": student_number,
        "atrisk_count": atrisk_count,
    }
    return render(request, "academics/index.html", ctx)


@login_required
def transcript(request):
    ext_id = request.GET.get("contactid") or request.GET.get("studentid")
    student = None
    if ext_id:
        student = Student.objects.filter(external_student_id=ext_id).first()
        if not student:
            return HttpResponseForbidden("forbidden")
    else:
        sid = request.session.get("active_student_id")
        if not sid:
            ctx = {
                "active_nav": "academics",
                "student": None,
                "header": {},
                "np_rows": [],
                "fb_rows": [],
                "p_rows": [],
                "no_student": True,
            }
            return render(request, "academics/transcript.html", ctx)
        student = Student.objects.filter(id=sid).first()
        if not student:
            ctx = {
                "active_nav": "academics",
                "student": None,
                "header": {},
                "np_rows": [],
                "fb_rows": [],
                "p_rows": [],
                "no_student": True,
            }
            return render(request, "academics/transcript.html", ctx)
        ext_id = student.external_student_id
    if not parent_can_view_student(request.user, student.id):
        return HttpResponseForbidden("forbidden")

    # Check for financial block
    contact = None
    if student.external_student_id:
        try:
             # Try local DB first (via model or fabric.py logic)
             if "fabric" in settings.DATABASES:
                 contact = fabric_contact_by_id(student.external_student_id)
        except Exception:
            pass
        if not contact and getattr(settings, "DYNAMICS_ORG_URL", ""):
            try:
                # Fallback to CRM service (which also checks local DB now)
                contact = get_contact_by_id(student.external_student_id)
            except Exception:
                pass
    
    if contact:
        # Check btfo_financeblock (boolean) or lk_bt_custonholdblocked (status)
        fin_block = contact.get("btfo_financeblock")
        if fin_block is True or str(fin_block).lower() == "true":
             return render(request, "academics/transcript_blocked.html", {
                 "active_nav": "academics",
                 "student": student,
                 "reason": "Financial Block"
             })


    f1 = (
        "<fetch distinct=\"true\">"
        "  <entity name=\"mshied_academicperioddetails\">"
        "    <filter>"
        f"      <condition attribute=\"mshied_studentid\" operator=\"eq\" value=\"{ext_id}\" />"
        "    </filter>"
        "    <link-entity name=\"mshied_program\" from=\"mshied_programid\" to=\"mshied_programid\" alias=\"prog\">"
        "      <attribute name=\"mshied_programid\" />"
        "      <attribute name=\"mshied_name\" />"
        "    </link-entity>"
        "  </entity>"
        "</fetch>"
    )
    r1 = fetchxml("mshied_academicperioddetails", f1)
    program_id = None
    program_name = None
    for row in r1.get("value", []):
        program_id = program_id or row.get("prog.mshied_programid")
        program_name = program_name or row.get("prog.mshied_name")
    if not program_id:
        program_id = ""

    ch_np = (
        "<fetch>"
        "  <entity name=\"mshied_coursehistory\">"
        "    <attribute name=\"mshied_name\" />"
        "    <attribute name=\"mshied_studentid\" />"
        "    <attribute name=\"bt_academicyear\" />"
        "    <order attribute=\"bt_academicyear\" descending=\"true\" />"
        "    <order attribute=\"createdon\" descending=\"true\" />"
        "    <filter>"
        f"      <condition attribute=\"mshied_studentid\" operator=\"eq\" value=\"{ext_id}\" uitype=\"contact\" />"
        "      <condition attribute=\"bt_published\" operator=\"ne\" value=\"1\" />"
        "      <condition attribute=\"statecode\" operator=\"eq\" value=\"0\" />"
        "    </filter>"
        "    <link-entity name=\"product\" from=\"productid\" to=\"bt_product\" alias=\"pr\">"
        "      <attribute name=\"msdyn_productnumber\" />"
        "    </link-entity>"
        "    <link-entity name=\"mshied_academicperioddetails\" from=\"mshied_academicperioddetailsid\" to=\"mshied_academicperioddetailsid\" alias=\"apd\">"
        "      <attribute name=\"bt_programstatus\" />"
        "      <attribute name=\"mshied_programid\" />"
        "      <filter>"
        "        <condition attribute=\"mshied_programid\" operator=\"not-null\" />"
        f"        <condition attribute=\"mshied_programid\" operator=\"eq\" value=\"{program_id}\" />"
        "      </filter>"
        "      <link-entity name=\"mshied_program\" from=\"mshied_programid\" to=\"mshied_programid\" alias=\"prog\">"
        "        <attribute name=\"mshied_name\" />"
        "        <attribute name=\"bt_nqflevel\" />"
        "        <attribute name=\"bt_saqaid\" />"
        "        <attribute name=\"bt_saqaidlevel\" />"
        "      </link-entity>"
        "    </link-entity>"
        "  </entity>"
        "</fetch>"
    )
    ch_fb = (
        "<fetch>"
        "  <entity name=\"mshied_coursehistory\">"
        "    <attribute name=\"mshied_name\" />"
        "    <attribute name=\"mshied_studentid\" />"
        "    <attribute name=\"bt_publishedresultcode\" />"
        "    <attribute name=\"bt_academicyear\" />"
        "    <attribute name=\"bt_publishedresultstatus\" />"
        "    <order attribute=\"bt_academicyear\" descending=\"true\" />"
        "    <order attribute=\"createdon\" descending=\"true\" />"
        "    <filter>"
        f"      <condition attribute=\"mshied_studentid\" operator=\"eq\" value=\"{ext_id}\" uitype=\"contact\" />"
        "      <condition attribute=\"bt_financialblock\" operator=\"eq\" value=\"1\" />"
        "      <condition attribute=\"bt_published\" operator=\"eq\" value=\"1\" />"
        "      <condition attribute=\"statecode\" operator=\"eq\" value=\"0\" />"
        "    </filter>"
        "    <link-entity name=\"product\" from=\"productid\" to=\"bt_product\" alias=\"pr\">"
        "      <attribute name=\"msdyn_productnumber\" />"
        "    </link-entity>"
        "    <link-entity name=\"mshied_academicperioddetails\" from=\"mshied_academicperioddetailsid\" to=\"mshied_academicperioddetailsid\" alias=\"apd\">"
        "      <attribute name=\"bt_programstatus\" />"
        "      <attribute name=\"mshied_programid\" />"
        "      <filter>"
        "        <condition attribute=\"mshied_programid\" operator=\"not-null\" />"
        f"        <condition attribute=\"mshied_programid\" operator=\"eq\" value=\"{program_id}\" />"
        "      </filter>"
        "      <link-entity name=\"mshied_program\" from=\"mshied_programid\" to=\"mshied_programid\" alias=\"prog\">"
        "        <attribute name=\"mshied_name\" />"
        "        <attribute name=\"bt_nqflevel\" />"
        "        <attribute name=\"bt_saqaid\" />"
        "        <attribute name=\"bt_saqaidlevel\" />"
        "      </link-entity>"
        "    </link-entity>"
        "  </entity>"
        "</fetch>"
    )
    ch_p = (
        "<fetch>"
        "  <entity name=\"mshied_coursehistory\">"
        "    <attribute name=\"mshied_name\" />"
        "    <attribute name=\"mshied_studentid\" />"
        "    <attribute name=\"bt_publishedexamaverage\" />"
        "    <attribute name=\"bt_publishedsemesteraverage\" />"
        "    <attribute name=\"bt_publishedfinalaverage\" />"
        "    <attribute name=\"bt_publishedresultcode\" />"
        "    <attribute name=\"bt_academicyear\" />"
        "    <attribute name=\"bt_publishedmodulestatus\" />"
        "    <attribute name=\"bt_publishedresultstatus\" />"
        "    <order attribute=\"bt_academicyear\" descending=\"true\" />"
        "    <order attribute=\"createdon\" descending=\"true\" />"
        "    <filter>"
        f"      <condition attribute=\"mshied_studentid\" operator=\"eq\" value=\"{ext_id}\" uitype=\"contact\" />"
        "      <condition attribute=\"bt_financialblock\" operator=\"ne\" value=\"1\" />"
        "      <condition attribute=\"bt_published\" operator=\"eq\" value=\"1\" />"
        "      <condition attribute=\"statecode\" operator=\"eq\" value=\"0\" />"
        "    </filter>"
        "    <link-entity name=\"product\" from=\"productid\" to=\"bt_product\" alias=\"pr\">"
        "      <attribute name=\"msdyn_productnumber\" />"
        "    </link-entity>"
        "    <link-entity name=\"mshied_academicperioddetails\" from=\"mshied_academicperioddetailsid\" to=\"mshied_academicperioddetailsid\" alias=\"apd\">"
        "      <attribute name=\"bt_programstatus\" />"
        "      <attribute name=\"mshied_programid\" />"
        "      <filter>"
        "        <condition attribute=\"mshied_programid\" operator=\"not-null\" />"
        f"        <condition attribute=\"mshied_programid\" operator=\"eq\" value=\"{program_id}\" />"
        "      </filter>"
        "      <link-entity name=\"mshied_program\" from=\"mshied_programid\" to=\"mshied_programid\" alias=\"prog\">"
        "        <attribute name=\"mshied_programid\" />"
        "        <attribute name=\"mshied_name\" />"
        "        <attribute name=\"bt_nqflevel\" />"
        "        <attribute name=\"bt_saqaid\" />"
        "        <attribute name=\"bt_saqaidlevel\" />"
        "      </link-entity>"
        "      <link-entity name=\"contact\" from=\"contactid\" to=\"mshied_studentid\" alias=\"contact\">"
        "        <attribute name=\"msdyn_contactpersonid\" />"
        "        <attribute name=\"msdyn_identificationnumber\" />"
        "        <attribute name=\"firstname\" />"
        "        <attribute name=\"lastname\" />"
        "      </link-entity>"
        "    </link-entity>"
        "  </entity>"
        "</fetch>"
    )

    def normalize(rows):
        out = []
        for r in rows or []:
            n = {}
            for k, v in r.items():
                if "@OData.Community.Display.V1.FormattedValue" in k:
                    base = k.split("@", 1)[0].replace(".", "__")
                    n[f"{base}__label"] = v
                else:
                    n[k.replace(".", "__")] = v
            out.append(n)
        return out

    np_rows = normalize(fetchxml("mshied_coursehistory", ch_np).get("value"))
    fb_rows = normalize(fetchxml("mshied_coursehistory", ch_fb).get("value"))
    p_rows = normalize(fetchxml("mshied_coursehistory", ch_p).get("value"))

    header = {}
    if p_rows:
        h = p_rows[0]
        header = {
            "name": f"{h.get('contact__firstname', '')} {h.get('contact__lastname', '')}".strip(),
            "student_number": h.get("contact__msdyn_contactpersonid"),
            "id_number": h.get("contact__msdyn_identificationnumber"),
            "program_status": h.get("apd__bt_programstatus__label"),
            "program_name": h.get("prog__mshied_name") or program_name,
        }
    else:
        header = {"program_name": program_name}

    ctx = {
        "active_nav": "academics",
        "student": student,
        "header": header,
        "np_rows": np_rows,
        "fb_rows": fb_rows,
        "p_rows": p_rows,
    }
    return render(request, "academics/transcript.html", ctx)


@login_required
def atrisk(request):
    ext_id = request.GET.get("contactid") or request.GET.get("studentid")
    student = None
    if ext_id:
        student = Student.objects.filter(external_student_id=ext_id).first()
        if not student:
            return HttpResponseForbidden("forbidden")
    else:
        sid = request.session.get("active_student_id")
        if not sid:
            ctx = {
                "active_nav": "academics",
                "student": None,
                "rows": [],
                "no_student": True,
            }
            return render(request, "academics/atrisk.html", ctx)
        student = Student.objects.filter(id=sid).first()
        if not student:
            ctx = {
                "active_nav": "academics",
                "student": None,
                "rows": [],
                "no_student": True,
            }
            return render(request, "academics/atrisk.html", ctx)
    if not parent_can_view_student(request.user, student.id):
        return HttpResponseForbidden("forbidden")

    rows = []
    if "fabric" in settings.DATABASES and student.external_student_id:
        try:
            rows = fetch_atrisk_for_student(student.external_student_id)
        except Exception:
            rows = []

    distinct_years = sorted({str(r.get("edv_year")) for r in rows if r.get("edv_year")}, reverse=True)
    distinct_blocks = sorted({str(r.get("edv_block")) for r in rows if r.get("edv_block")})

    req_year = request.GET.get("year")
    req_block = request.GET.get("block")
    q = (request.GET.get("q") or "").lower().strip()

    filtered_rows = []
    for r in rows:
        # Year filter
        if req_year and str(r.get("edv_year")) != req_year:
            continue
        # Block filter
        if req_block and str(r.get("edv_block")) != req_block:
            continue
        # Search filter
        if q:
            searchable = [
                str(r.get("edv_modulecode") or ""),
                str(r.get("edv_primaryreason") or ""),
                str(r.get("edv_secondaryreason") or ""),
                str(r.get("edv_comments") or ""),
            ]
            if not any(q in s.lower() for s in searchable):
                continue
        filtered_rows.append(r)

    ctx = {
        "active_nav": "academics",
        "student": student,
        "rows": filtered_rows,
        "distinct_years": distinct_years,
        "distinct_blocks": distinct_blocks,
    }
    return render(request, "academics/atrisk.html", ctx)
