from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, List, Tuple

from django.conf import settings
from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from academics.models import GradeItem
from attendance.models import AttendanceRecord
from content.models import Document
from content.services import get_notice_buckets_for_user
from crm.service import get_contact_balance
from students.fabric import fetch_atrisk_for_student
from students.models import ParentStudentLink

WINDOW_DAYS = 7
CACHE_TTL_SECONDS = 6 * 60 * 60
MAX_ITEMS = 5
ATTENDANCE_ALERTS = {"ABSENT", "LATE"}


def _window_key(start: timezone.datetime) -> str:
    return start.strftime("%Y-%m-%d")


def _cache_key(prefix: str, entity_id: str, window_key: str) -> str:
    return f"digest:v3:{prefix}:{entity_id}:{window_key}"


def _student_label(first_name: str, last_name: str, fallback: int) -> str:
    name = f"{first_name} {last_name}".strip()
    return name or f"Student {fallback}"


def _transcript_summary(student_id: int, window_key: str) -> Dict[str, Any]:
    cache_id = _cache_key("transcript", str(student_id), window_key)
    cached = cache.get(cache_id)
    if cached is not None:
        return cached
    grades = (
        GradeItem.objects.filter(
            enrollment__student_id=student_id,
            status="PUBLISHED",
        )
        .select_related("enrollment__module")
        .order_by("-published_at", "-id")[:MAX_ITEMS]
    )
    modules: List[Dict[str, Any]] = []
    for gi in grades:
        module = gi.enrollment.module
        modules.append(
            {
                "module": getattr(module, "title", None) or module.code,
                "code": getattr(module, "code", ""),
                "percentage": (
                    float(gi.percentage) if gi.percentage is not None else None
                ),
                "status": gi.status,
                "published_at": (
                    gi.published_at.isoformat() if gi.published_at else None
                ),
            }
        )
    summary = {"modules": modules, "has_data": bool(modules)}
    cache.set(cache_id, summary, CACHE_TTL_SECONDS)
    return summary


def _format_row_date(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "date"):
        try:
            dt = value
            if timezone.is_aware(dt):
                dt = timezone.localtime(dt)
            return dt.date().isoformat()
        except Exception:
            return ""
    if isinstance(value, str):
        dt = parse_datetime(value)
        if dt is not None:
            if timezone.is_aware(dt):
                dt = timezone.localtime(dt)
            return dt.date().isoformat()
        d = parse_date(value)
        if d is not None:
            return d.isoformat()
    return ""


def _atrisk_summary(
    external_id: str | None,
    window_key: str,
) -> Dict[str, Any]:
    if not external_id or "fabric" not in settings.DATABASES:
        return {"items": [], "has_data": False}
    cache_id = _cache_key("atrisk", external_id, window_key)
    cached = cache.get(cache_id)
    if cached is not None:
        return cached
    try:
        rows = fetch_atrisk_for_student(
            external_id,
            limit=50,
        ) or []
    except Exception:
        rows = []
    items: List[Dict[str, Any]] = []
    for row in rows[:MAX_ITEMS]:
        created_on = _format_row_date(row.get("createdon"))
        year = row.get("edv_year")
        week = row.get("edv_week")
        fallback_label = ""
        if year and week:
            fallback_label = f"Y{year} W{week}"
        items.append(
            {
                "date": created_on or fallback_label,
                "module_code": row.get("edv_modulecode"),
                "primary_reason": row.get("edv_primaryreason"),
                "secondary_reason": row.get("edv_secondaryreason"),
                "comments": row.get("edv_comments"),
                "block": row.get("edv_block"),
                "year": year,
                "week": week,
            }
        )
    summary = {"items": items, "has_data": bool(items)}
    cache.set(cache_id, summary, CACHE_TTL_SECONDS)
    return summary


def _attendance_summary(
    student_id: int,
    window_start: timezone.datetime,
    window_key: str,
) -> Dict[str, Any]:
    cache_id = _cache_key("attendance", str(student_id), window_key)
    cached = cache.get(cache_id)
    if cached is not None:
        return cached
    records = (
        AttendanceRecord.objects.filter(
            enrollment__student_id=student_id,
            date__gte=window_start.date(),
        )
        .select_related("enrollment__module")
        .order_by("-date")
    )
    counts = {choice[0]: 0 for choice in AttendanceRecord.STATUS_CHOICES}
    flags: List[Dict[str, Any]] = []
    for record in records:
        counts[record.status] = counts.get(record.status, 0) + 1
        if record.status in ATTENDANCE_ALERTS:
            flags.append(
                {
                    "date": record.date.isoformat(),
                    "status": record.status,
                    "module": getattr(record.enrollment.module, "title", None),
                    "note": record.note,
                }
            )
    summary = {
        "counts": counts,
        "total": sum(counts.values()),
        "alerts": len(flags),
        "flagged": flags[:MAX_ITEMS],
    }
    cache.set(cache_id, summary, CACHE_TTL_SECONDS)
    return summary


def _financial_summary(
    external_id: str | None,
    window_key: str,
) -> Dict[str, Any]:
    if not external_id:
        return {
            "status": "unknown",
            "label": "Balance: unavailable",
            "amount": None,
        }
    cache_id = _cache_key("financial", external_id, window_key)
    cached = cache.get(cache_id)
    if cached is not None:
        return cached
    status = "unknown"
    amount = None
    label = None
    info = get_contact_balance(external_id)
    if info:
        formatted = info.get("formatted")
        label = formatted
        raw_amount = info.get("amount")
        if raw_amount is not None:
            try:
                amount = float(raw_amount)
            except (TypeError, ValueError):
                amount = None
        if amount is not None:
            status = "due" if amount > 0 else "clear"
            if formatted:
                if amount > 0:
                    label = f"Current Payment Due: {formatted}"
                elif amount < 0:
                    label = f"Currently no payment due: {formatted}"
                else:
                    label = f"Balance: {formatted}"
        elif label:
            status = "info"
    if not label:
        if amount is not None:
            label = f"Balance: R {amount:,.2f}"
        else:
            label = "Balance: unavailable"
    summary = {"status": status, "label": label, "amount": amount}
    cache.set(cache_id, summary, CACHE_TTL_SECONDS)
    return summary


def _documents_summary(student_id: int, window_key: str) -> Dict[str, Any]:
    cache_id = _cache_key("documents", str(student_id), window_key)
    cached = cache.get(cache_id)
    if cached is not None:
        return cached
    docs = (
        Document.objects.filter(
            Q(is_public=True) | Q(student_id=student_id),
        )
        .order_by("-published_at")[:MAX_ITEMS]
    )
    items = [
        {
            "title": doc.title,
            "category": doc.category,
            "published_at": (
                doc.published_at.isoformat() if doc.published_at else None
            ),
            "url": doc.file_url,
            "student_specific": doc.student_id is not None,
        }
        for doc in docs
    ]
    summary = {"items": items, "has_data": bool(items)}
    cache.set(cache_id, summary, CACHE_TTL_SECONDS)
    return summary


def _announcements_summary(
    user,
) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, int]]:
    buckets = get_notice_buckets_for_user(user, window_days=WINDOW_DAYS)
    serialized: Dict[str, List[Dict[str, Any]]] = {}
    counts: Dict[str, int] = {}
    for bucket, items in buckets.items():
        counts[bucket] = len(items)
        serialized[bucket] = [
            {
                "id": ann.id,
                "title": ann.title,
                "published_at": (
                    timezone.localtime(ann.published_at).strftime("%Y-%m-%d")
                    if ann.published_at
                    else ""
                ),
                "severity": getattr(ann, "severity", ""),
                "category": getattr(ann, "category", ""),
            }
            for ann in items[:MAX_ITEMS]
        ]
    counts["total"] = sum(counts.values())
    return serialized, counts


def build_weekly_digest(user) -> Dict[str, Any]:
    now = timezone.now()
    window_start = now - timedelta(days=WINDOW_DAYS)
    window_key = _window_key(window_start)
    cache_id = _cache_key("user", str(user.id), window_key)
    cached = cache.get(cache_id)
    if cached is not None:
        return cached

    links = (
        ParentStudentLink.objects.select_related("student")
        .filter(user=user, active=True)
        .order_by("student__first_name", "student__last_name")
    )

    students: List[Dict[str, Any]] = []
    attendance_flags = 0
    financial_due = 0

    for link in links:
        student = link.student
        if not student:
            continue
        transcript = _transcript_summary(student.id, window_key)
        atrisk = _atrisk_summary(student.external_student_id, window_key)
        attendance = _attendance_summary(student.id, window_start, window_key)
        financial = _financial_summary(student.external_student_id, window_key)
        documents = _documents_summary(student.id, window_key)

        attendance_flags += attendance["alerts"]
        if financial.get("status") == "due":
            financial_due += 1

        students.append(
            {
                "id": student.id,
                "name": _student_label(
                    student.first_name,
                    student.last_name,
                    student.id,
                ),
                "transcript": transcript,
                "atrisk": atrisk,
                "attendance": attendance,
                "financial": financial,
                "documents": documents,
            }
        )

    primary_student_name = students[0]["name"] if len(students) == 1 else None

    announcements, announcement_counts = _announcements_summary(user)
    total_count = announcement_counts.get("total", 0)
    announcement_sections = []
    for bucket in ["personal", "student", "module", "general"]:
        entries = announcements.get(bucket, [])
        announcement_sections.append(
            {
                "name": bucket,
                "count": announcement_counts.get(bucket, 0),
                "items": entries,
                "has_data": bool(entries),
            }
        )

    subject_vars = {
        "first": getattr(user, "first_name", "") or user.email,
        "students": len(students),
        "total": total_count,
        "personal_count": announcement_counts.get("personal", 0),
        "student_count": announcement_counts.get("student", 0),
        "module_count": announcement_counts.get("module", 0),
        "general_count": announcement_counts.get("general", 0),
        "attendance_flags": attendance_flags,
        "financial_due": financial_due,
        "student_name": primary_student_name,
        "subject": (
            f"Your Eduvos Notices for Student: {primary_student_name}"
            if primary_student_name
            else (
                "Your Eduvos Notices"
                if total_count == 0
                else f"Your Eduvos Notices ({total_count})"
            )
        ),
    }

    digest = {
        "generated_at": now,
        "window_start": window_start.date(),
        "window_end": now.date(),
        "students": students,
        "announcements": announcements,
        "announcement_counts": announcement_counts,
        "announcement_sections": announcement_sections,
        "notices": announcements,
        "notices_counts": announcement_counts,
        "subject_vars": subject_vars,
    }
    cache.set(cache_id, digest, CACHE_TTL_SECONDS)
    return digest
