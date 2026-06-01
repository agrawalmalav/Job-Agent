from __future__ import annotations

import re
from dataclasses import asdict
from datetime import date, datetime
from typing import Any

from .company_utils import normalize_company_name
from .models import BasicFilterResult, Job, PIPELINE_STATUSES, SponsorResult, USER_STATUSES
from .supabase_client import get_supabase_client
from .utils import json_dumps


_APIFY_ID_CACHE: set[str] | None = None
_APIFY_ID_TO_ID_CACHE: dict[str, int] | None = None


JOB_COLUMNS = [
    "source",
    "apify_id",
    "title",
    "standardized_title",
    "company_name",
    "country",
    "location",
    "posted_at",
    "posted_at_timestamp",
    "expire_at",
    "employment_type",
    "seniority_level",
    "job_function",
    "industries",
    "description_text",
    "apply_method",
    "apply_url",
    "linkedin_url",
    "applicants_count",
    "salary",
    "min_salary",
    "max_salary",
    "currency_code",
    "pay_period",
    "work_remote_allowed",
    "workplace_type",
    "company_linkedin_url",
    "sponsor_status",
    "sponsor_confidence",
    "sponsor_matched_by",
    "sponsor_search_terms",
    "sponsor_matched_name",
    "sponsor_matched_rows",
    "pipeline_status",
    "user_status",
    "user_notes",
    "applied_at",
    "referral_requested_at",
    "interview_scheduled_at",
    "closed_at",
    "final_score",
    "created_at",
    "updated_at",
    "fetched_date",
    "status",
    "rejection_stage",
    "rejection_reason",
    "matched_rejection_keywords",
]


def init_db(db_path=None) -> None:
    return None


def _normalize_signature(value: str | None) -> str:
    if not value:
        return ""
    normalized = re.sub(r"[^a-z0-9]+", " ", value.lower())
    return re.sub(r"\s+", " ", normalized).strip()


def _execute(response):
    data = getattr(response, "data", None)
    return data if data is not None else response


def _existing_apify_ids() -> set[str]:
    global _APIFY_ID_CACHE, _APIFY_ID_TO_ID_CACHE
    if _APIFY_ID_CACHE is not None:
        return _APIFY_ID_CACHE

    client = get_supabase_client()
    apify_ids: set[str] = set()
    apify_id_to_id: dict[str, int] = {}
    start = 0
    page_size = 1000
    while True:
        response = (
            client.table("jobs")
            .select("id,apify_id")
            .range(start, start + page_size - 1)
            .execute()
        )
        batch = _execute(response) or []
        for row in batch:
            if row.get("apify_id"):
                apify_id = str(row["apify_id"])
                apify_ids.add(apify_id)
                if row.get("id") is not None:
                    apify_id_to_id[apify_id] = row["id"]
        if len(batch) < page_size:
            break
        start += page_size

    _APIFY_ID_CACHE = apify_ids
    _APIFY_ID_TO_ID_CACHE = apify_id_to_id
    return _APIFY_ID_CACHE


def _is_duplicate_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "23505" in text or "duplicate key value" in text


def _select_first_by(column: str, value: str | None) -> dict | None:
    if not value:
        return None
    response = (
        get_supabase_client()
        .table("jobs")
        .select("*")
        .eq(column, value)
        .limit(1)
        .execute()
    )
    rows = _execute(response) or []
    return rows[0] if rows else None


def _all_signature_rows() -> list[dict]:
    response = (
        get_supabase_client()
        .table("jobs")
        .select("id,company_name,title,location")
        .execute()
    )
    return _execute(response) or []


def find_duplicate_job(db_path, job: Job) -> dict | None:
    if job.apify_id and str(job.apify_id) in _existing_apify_ids():
        apify_id = str(job.apify_id)
        return {"id": (_APIFY_ID_TO_ID_CACHE or {}).get(apify_id), "apify_id": job.apify_id}
    return None


def job_exists(db_path, linkedin_url, apply_url, apify_id, job: Job | None = None) -> bool:
    if apify_id and str(apify_id) in _existing_apify_ids():
        return True
    if job is not None and job.apify_id and str(job.apify_id) in _existing_apify_ids():
        return True
    return False


def insert_job(
    db_path,
    job: Job,
    sponsor_result: SponsorResult,
    filter_result: BasicFilterResult,
    pipeline_status: str,
    final_score: int,
) -> bool:
    if job.apify_id and str(job.apify_id) in _existing_apify_ids():
        return False

    now = datetime.now().isoformat(timespec="seconds")
    job_data = asdict(job)
    job_data.pop("raw", None)
    row: dict[str, Any] = {
        **job_data,
        "sponsor_status": sponsor_result.status,
        "sponsor_confidence": sponsor_result.confidence,
        "sponsor_matched_by": sponsor_result.matched_by,
        "sponsor_search_terms": json_dumps(sponsor_result.search_terms),
        "sponsor_matched_name": sponsor_result.matched_name,
        "sponsor_matched_rows": json_dumps(sponsor_result.matched_rows),
        "pipeline_status": pipeline_status,
        "user_status": "pending",
        "user_notes": None,
        "applied_at": None,
        "referral_requested_at": None,
        "interview_scheduled_at": None,
        "closed_at": None,
        "final_score": final_score,
        "created_at": now,
        "updated_at": now,
        "fetched_date": date.today().isoformat(),
        "status": pipeline_status,
        "rejection_stage": filter_result.rejection_stage,
        "rejection_reason": filter_result.rejection_reason,
        "matched_rejection_keywords": json_dumps(filter_result.matched_keywords),
    }
    payload = {column: row.get(column) for column in JOB_COLUMNS}
    try:
        get_supabase_client().table("jobs").insert(payload).execute()
    except Exception as exc:
        if _is_duplicate_error(exc):
            if job.apify_id:
                _existing_apify_ids().add(str(job.apify_id))
            return False
        raise
    if job.apify_id:
        apify_id = str(job.apify_id)
        _existing_apify_ids().add(apify_id)
        if _APIFY_ID_TO_ID_CACHE is not None:
            _APIFY_ID_TO_ID_CACHE[apify_id] = payload.get("id")
    return True


def get_jobs(db_path, filters: dict | None = None) -> list[dict]:
    filters = filters or {}
    query = get_supabase_client().table("jobs").select("*")
    for key in (
        "pipeline_status",
        "user_status",
        "sponsor_status",
        "fetched_date",
        "employment_type",
        "workplace_type",
    ):
        if filters.get(key):
            query = query.eq(key, filters[key])
    if filters.get("company_search"):
        query = query.ilike("company_name", f"%{filters['company_search']}%")
    if filters.get("location_search"):
        query = query.ilike("location", f"%{filters['location_search']}%")
    if filters.get("posted_date"):
        query = query.or_(
            f"posted_at.ilike.%{filters['posted_date']}%,posted_at_timestamp.ilike.%{filters['posted_date']}%"
        )
    if filters.get("keyword"):
        keyword = filters["keyword"]
        query = query.or_(
            "title.ilike.%{0}%,company_name.ilike.%{0}%,location.ilike.%{0}%,description_text.ilike.%{0}%".format(
                keyword
            )
        )

    response = (
        query.order("fetched_date", desc=True)
        .order("posted_at_timestamp", desc=True)
        .order("created_at", desc=True)
        .execute()
    )
    return _execute(response) or []


def get_jobs_by_date(db_path, fetched_date: str, status: str | None = None) -> list[dict]:
    filters: dict[str, Any] = {"fetched_date": fetched_date}
    if status:
        filters["pipeline_status"] = status
    return get_jobs(db_path, filters)


def update_user_status(db_path, job_id: int, user_status: str, notes: str | None = None) -> None:
    if user_status not in USER_STATUSES:
        raise ValueError(f"Invalid user_status: {user_status}")
    now = datetime.now().isoformat(timespec="seconds")
    payload: dict[str, Any] = {"user_status": user_status, "updated_at": now}
    timestamp_column = {
        "applied": "applied_at",
        "referral_requested": "referral_requested_at",
        "interview_scheduled": "interview_scheduled_at",
        "closed": "closed_at",
    }.get(user_status)
    if timestamp_column:
        existing = _select_first_by("id", str(job_id)) or {}
        payload[timestamp_column] = existing.get(timestamp_column) or now
    if notes is not None:
        payload["user_notes"] = notes
    get_supabase_client().table("jobs").update(payload).eq("id", job_id).execute()


def update_user_notes(db_path, job_id: int, notes: str) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    get_supabase_client().table("jobs").update({"user_notes": notes, "updated_at": now}).eq("id", job_id).execute()


def update_pipeline_status(db_path, job_id: int, pipeline_status: str) -> None:
    if pipeline_status not in PIPELINE_STATUSES:
        raise ValueError(f"Invalid pipeline_status: {pipeline_status}")
    now = datetime.now().isoformat(timespec="seconds")
    get_supabase_client().table("jobs").update(
        {"pipeline_status": pipeline_status, "status": pipeline_status, "updated_at": now}
    ).eq("id", job_id).execute()


def update_pipeline_result(
    db_path,
    job_id: int,
    sponsor_result: SponsorResult,
    filter_result: BasicFilterResult,
    pipeline_status: str,
    final_score: int,
) -> None:
    if pipeline_status not in PIPELINE_STATUSES:
        raise ValueError(f"Invalid pipeline_status: {pipeline_status}")
    now = datetime.now().isoformat(timespec="seconds")
    payload = {
        "sponsor_status": sponsor_result.status,
        "sponsor_confidence": sponsor_result.confidence,
        "sponsor_matched_by": sponsor_result.matched_by,
        "sponsor_search_terms": json_dumps(sponsor_result.search_terms),
        "sponsor_matched_name": sponsor_result.matched_name,
        "sponsor_matched_rows": json_dumps(sponsor_result.matched_rows),
        "pipeline_status": pipeline_status,
        "status": pipeline_status,
        "rejection_stage": filter_result.rejection_stage,
        "rejection_reason": filter_result.rejection_reason,
        "matched_rejection_keywords": json_dumps(filter_result.matched_keywords),
        "final_score": final_score,
        "updated_at": now,
    }
    get_supabase_client().table("jobs").update(payload).eq("id", job_id).execute()


def get_job_stats(db_path) -> dict:
    rows = get_jobs(db_path)
    stats: dict[str, Any] = {"pipeline_status": {}, "user_status": {}, "sponsor_status": {}, "total": len(rows)}
    for column in ("pipeline_status", "user_status", "sponsor_status"):
        for row in rows:
            value = row.get(column) or ""
            stats[column][value] = stats[column].get(value, 0) + 1
    return stats


def get_distinct_fetched_dates(db_path) -> list[str]:
    rows = get_jobs(db_path)
    return sorted({row["fetched_date"] for row in rows if row.get("fetched_date")}, reverse=True)


def get_latest_fetch_date(db_path) -> str | None:
    dates = get_distinct_fetched_dates(db_path)
    return dates[0] if dates else None


def get_agency_company(db_path, company_name: str) -> dict | None:
    normalized = normalize_company_name(company_name)
    if not normalized:
        return None
    response = (
        get_supabase_client()
        .table("agency_companies")
        .select("*")
        .eq("normalized_company_name", normalized)
        .limit(1)
        .execute()
    )
    rows = _execute(response) or []
    return rows[0] if rows else None


def is_agency_company(db_path, company_name: str) -> bool:
    return get_agency_company(db_path, company_name) is not None


def upsert_agency_company(db_path, company_name: str, notes: str | None = None, added_by: str | None = None) -> None:
    normalized = normalize_company_name(company_name)
    if not normalized:
        raise ValueError("company_name cannot be empty")
    now = datetime.now().isoformat(timespec="seconds")
    payload = {
        "company_name": company_name,
        "normalized_company_name": normalized,
        "notes": notes,
        "added_by": added_by,
        "updated_at": now,
    }
    existing = get_agency_company(db_path, company_name)
    if not existing:
        payload["created_at"] = now
    get_supabase_client().table("agency_companies").upsert(
        payload,
        on_conflict="normalized_company_name",
    ).execute()


def apply_agency_status_to_jobs(db_path, company_name: str) -> int:
    normalized = normalize_company_name(company_name)
    if not normalized:
        return 0
    rows = get_jobs(db_path)
    matching_ids = [
        row["id"]
        for row in rows
        if normalize_company_name(row.get("company_name") or "") == normalized and row.get("id") is not None
    ]
    if not matching_ids:
        return 0
    now = datetime.now().isoformat(timespec="seconds")
    payload = {
        "sponsor_status": "agency",
        "sponsor_confidence": "high",
        "sponsor_matched_by": "manual_agency",
        "sponsor_search_terms": json_dumps([normalized]),
        "sponsor_matched_name": company_name,
        "sponsor_matched_rows": "",
        "pipeline_status": "manual_review",
        "status": "manual_review",
        "rejection_stage": None,
        "rejection_reason": "Recruitment agency / actual employer unknown",
        "matched_rejection_keywords": "",
        "final_score": 5,
        "updated_at": now,
    }
    get_supabase_client().table("jobs").update(payload).in_("id", matching_ids).execute()
    return len(matching_ids)
