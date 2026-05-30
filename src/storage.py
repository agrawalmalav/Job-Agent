from __future__ import annotations

import re
import sqlite3
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .models import BasicFilterResult, Job, PIPELINE_STATUSES, SponsorResult, USER_STATUSES
from .utils import ensure_dir, json_dumps


JOB_COLUMNS = [
    "fetched_date",
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
    "status",
    "pipeline_status",
    "user_status",
    "user_notes",
    "applied_at",
    "referral_requested_at",
    "interview_scheduled_at",
    "closed_at",
    "updated_at",
    "rejection_stage",
    "rejection_reason",
    "matched_rejection_keywords",
    "final_score",
    "created_at",
]

SCHEMA_COLUMNS = {
    "fetched_date": "TEXT",
    "source": "TEXT",
    "apify_id": "TEXT",
    "title": "TEXT",
    "standardized_title": "TEXT",
    "company_name": "TEXT",
    "country": "TEXT",
    "location": "TEXT",
    "posted_at": "TEXT",
    "posted_at_timestamp": "TEXT",
    "expire_at": "TEXT",
    "employment_type": "TEXT",
    "seniority_level": "TEXT",
    "job_function": "TEXT",
    "industries": "TEXT",
    "description_text": "TEXT",
    "apply_method": "TEXT",
    "apply_url": "TEXT",
    "linkedin_url": "TEXT",
    "applicants_count": "TEXT",
    "salary": "TEXT",
    "min_salary": "TEXT",
    "max_salary": "TEXT",
    "currency_code": "TEXT",
    "pay_period": "TEXT",
    "work_remote_allowed": "TEXT",
    "workplace_type": "TEXT",
    "company_linkedin_url": "TEXT",
    "sponsor_status": "TEXT",
    "sponsor_confidence": "TEXT",
    "sponsor_matched_by": "TEXT",
    "sponsor_search_terms": "TEXT",
    "sponsor_matched_name": "TEXT",
    "sponsor_matched_rows": "TEXT",
    "status": "TEXT",
    "pipeline_status": "TEXT",
    "user_status": "TEXT DEFAULT 'pending'",
    "user_notes": "TEXT",
    "applied_at": "TEXT",
    "referral_requested_at": "TEXT",
    "interview_scheduled_at": "TEXT",
    "closed_at": "TEXT",
    "updated_at": "TEXT",
    "rejection_stage": "TEXT",
    "rejection_reason": "TEXT",
    "matched_rejection_keywords": "TEXT",
    "final_score": "INTEGER",
    "created_at": "TEXT",
}


def _connect(db_path: str | Path) -> sqlite3.Connection:
    ensure_dir(Path(db_path).parent)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def _columns(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute("PRAGMA table_info(jobs)").fetchall()
    return {row["name"] for row in rows}


def init_db(db_path: str | Path) -> None:
    with _connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fetched_date TEXT,
                source TEXT,
                apify_id TEXT,
                title TEXT,
                standardized_title TEXT,
                company_name TEXT,
                country TEXT,
                location TEXT,
                posted_at TEXT,
                posted_at_timestamp TEXT,
                expire_at TEXT,
                employment_type TEXT,
                seniority_level TEXT,
                job_function TEXT,
                industries TEXT,
                description_text TEXT,
                apply_method TEXT,
                apply_url TEXT,
                linkedin_url TEXT,
                applicants_count TEXT,
                salary TEXT,
                min_salary TEXT,
                max_salary TEXT,
                currency_code TEXT,
                pay_period TEXT,
                work_remote_allowed TEXT,
                workplace_type TEXT,
                company_linkedin_url TEXT,
                sponsor_status TEXT,
                sponsor_confidence TEXT,
                sponsor_matched_by TEXT,
                sponsor_search_terms TEXT,
                sponsor_matched_name TEXT,
                sponsor_matched_rows TEXT,
                status TEXT,
                pipeline_status TEXT,
                user_status TEXT DEFAULT 'pending',
                user_notes TEXT,
                applied_at TEXT,
                referral_requested_at TEXT,
                interview_scheduled_at TEXT,
                closed_at TEXT,
                updated_at TEXT,
                rejection_stage TEXT,
                rejection_reason TEXT,
                matched_rejection_keywords TEXT,
                final_score INTEGER,
                created_at TEXT
            )
            """
        )
        existing_columns = _columns(connection)
        for column, definition in SCHEMA_COLUMNS.items():
            if column not in existing_columns:
                connection.execute(f"ALTER TABLE jobs ADD COLUMN {column} {definition}")
        existing_columns = _columns(connection)
        if "status" in existing_columns and "pipeline_status" in existing_columns:
            connection.execute(
                "UPDATE jobs SET pipeline_status = status WHERE pipeline_status IS NULL AND status IS NOT NULL"
            )
        connection.execute("UPDATE jobs SET user_status = 'pending' WHERE user_status IS NULL OR user_status = ''")
        connection.commit()


def _normalize_signature(value: str | None) -> str:
    if not value:
        return ""
    normalized = re.sub(r"[^a-z0-9]+", " ", value.lower())
    return re.sub(r"\s+", " ", normalized).strip()


def _duplicate_by_urls(
    connection: sqlite3.Connection,
    linkedin_url: str | None,
    apply_url: str | None,
    apify_id: str | None,
) -> sqlite3.Row | None:
    checks = []
    params: list[str] = []
    for column, value in (
        ("linkedin_url", linkedin_url),
        ("apply_url", apply_url),
        ("apify_id", apify_id),
    ):
        if value:
            checks.append(f"{column} = ?")
            params.append(value)
    if not checks:
        return None
    return connection.execute(
        f"SELECT * FROM jobs WHERE {' OR '.join(checks)} LIMIT 1",
        params,
    ).fetchone()


def _duplicate_by_signature(connection: sqlite3.Connection, job: Job) -> sqlite3.Row | None:
    target = (
        _normalize_signature(job.company_name),
        _normalize_signature(job.title),
        _normalize_signature(job.location),
    )
    if not any(target):
        return None

    rows = connection.execute(
        "SELECT * FROM jobs WHERE company_name IS NOT NULL AND title IS NOT NULL"
    ).fetchall()
    for row in rows:
        candidate = (
            _normalize_signature(row["company_name"]),
            _normalize_signature(row["title"]),
            _normalize_signature(row["location"]),
        )
        if candidate == target:
            return row
    return None


def find_duplicate_job(db_path: str | Path, job: Job) -> dict | None:
    with _connect(db_path) as connection:
        row = _duplicate_by_urls(connection, job.linkedin_url, job.apply_url, job.apify_id)
        if row is None:
            row = _duplicate_by_signature(connection, job)
    return dict(row) if row else None


def job_exists(
    db_path: str | Path,
    linkedin_url: str | None,
    apply_url: str | None,
    apify_id: str | None,
    job: Job | None = None,
) -> bool:
    with _connect(db_path) as connection:
        row = _duplicate_by_urls(connection, linkedin_url, apply_url, apify_id)
        if row is None and job is not None:
            row = _duplicate_by_signature(connection, job)
    return row is not None


def insert_job(
    db_path: str | Path,
    job: Job,
    sponsor_result: SponsorResult,
    filter_result: BasicFilterResult,
    pipeline_status: str,
    final_score: int,
) -> bool:
    if find_duplicate_job(db_path, job):
        return False

    now = datetime.now().isoformat(timespec="seconds")
    job_data = asdict(job)
    job_data.pop("raw", None)
    row: dict[str, Any] = {
        "fetched_date": date.today().isoformat(),
        **job_data,
        "sponsor_status": sponsor_result.status,
        "sponsor_confidence": sponsor_result.confidence,
        "sponsor_matched_by": sponsor_result.matched_by,
        "sponsor_search_terms": json_dumps(sponsor_result.search_terms),
        "sponsor_matched_name": sponsor_result.matched_name,
        "sponsor_matched_rows": json_dumps(sponsor_result.matched_rows),
        "status": pipeline_status,
        "pipeline_status": pipeline_status,
        "user_status": "pending",
        "user_notes": None,
        "applied_at": None,
        "referral_requested_at": None,
        "interview_scheduled_at": None,
        "closed_at": None,
        "updated_at": now,
        "rejection_stage": filter_result.rejection_stage,
        "rejection_reason": filter_result.rejection_reason,
        "matched_rejection_keywords": json_dumps(filter_result.matched_keywords),
        "final_score": final_score,
        "created_at": now,
    }

    placeholders = ", ".join("?" for _ in JOB_COLUMNS)
    columns = ", ".join(JOB_COLUMNS)
    values = [row.get(column) for column in JOB_COLUMNS]
    with _connect(db_path) as connection:
        connection.execute(
            f"INSERT INTO jobs ({columns}) VALUES ({placeholders})",
            values,
        )
        connection.commit()
    return True


def get_jobs(db_path: str | Path, filters: dict | None = None) -> list[dict]:
    filters = filters or {}
    query = "SELECT * FROM jobs WHERE 1 = 1"
    params: list[Any] = []

    exact_filters = {
        "pipeline_status": "pipeline_status",
        "user_status": "user_status",
        "sponsor_status": "sponsor_status",
        "fetched_date": "fetched_date",
        "employment_type": "employment_type",
        "workplace_type": "workplace_type",
    }
    for key, column in exact_filters.items():
        value = filters.get(key)
        if value:
            query += f" AND {column} = ?"
            params.append(value)

    company_search = filters.get("company_search")
    if company_search:
        query += " AND LOWER(company_name) LIKE ?"
        params.append(f"%{company_search.lower()}%")

    location_search = filters.get("location_search")
    if location_search:
        query += " AND LOWER(COALESCE(location, '')) LIKE ?"
        params.append(f"%{location_search.lower()}%")

    keyword = filters.get("keyword")
    if keyword:
        like = f"%{keyword.lower()}%"
        query += """
            AND (
                LOWER(COALESCE(title, '')) LIKE ?
                OR LOWER(COALESCE(company_name, '')) LIKE ?
                OR LOWER(COALESCE(location, '')) LIKE ?
                OR LOWER(COALESCE(description_text, '')) LIKE ?
            )
        """
        params.extend([like, like, like, like])

    posted_date = filters.get("posted_date")
    if posted_date:
        query += " AND COALESCE(posted_at, posted_at_timestamp, '') LIKE ?"
        params.append(f"%{posted_date}%")

    query += " ORDER BY fetched_date DESC, posted_at_timestamp DESC, posted_at DESC, created_at DESC"

    with _connect(db_path) as connection:
        rows = connection.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def get_jobs_by_date(db_path: str | Path, fetched_date: str, status: str | None = None) -> list[dict]:
    filters: dict[str, Any] = {"fetched_date": fetched_date}
    if status:
        filters["pipeline_status"] = status
    return get_jobs(db_path, filters)


def update_user_status(db_path: str | Path, job_id: int, user_status: str, notes: str | None = None) -> None:
    if user_status not in USER_STATUSES:
        raise ValueError(f"Invalid user_status: {user_status}")

    now = datetime.now().isoformat(timespec="seconds")
    assignments = ["user_status = ?", "updated_at = ?"]
    params: list[Any] = [user_status, now]
    timestamp_column = {
        "applied": "applied_at",
        "referral_requested": "referral_requested_at",
        "interview_scheduled": "interview_scheduled_at",
        "closed": "closed_at",
    }.get(user_status)
    if timestamp_column:
        assignments.append(f"{timestamp_column} = COALESCE({timestamp_column}, ?)")
        params.append(now)
    if notes is not None:
        assignments.append("user_notes = ?")
        params.append(notes)
    params.append(job_id)

    with _connect(db_path) as connection:
        connection.execute(
            f"UPDATE jobs SET {', '.join(assignments)} WHERE id = ?",
            params,
        )
        connection.commit()


def update_user_notes(db_path: str | Path, job_id: int, notes: str) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    with _connect(db_path) as connection:
        connection.execute(
            "UPDATE jobs SET user_notes = ?, updated_at = ? WHERE id = ?",
            (notes, now, job_id),
        )
        connection.commit()


def update_pipeline_status(db_path: str | Path, job_id: int, pipeline_status: str) -> None:
    if pipeline_status not in PIPELINE_STATUSES:
        raise ValueError(f"Invalid pipeline_status: {pipeline_status}")

    now = datetime.now().isoformat(timespec="seconds")
    with _connect(db_path) as connection:
        connection.execute(
            "UPDATE jobs SET pipeline_status = ?, status = ?, updated_at = ? WHERE id = ?",
            (pipeline_status, pipeline_status, now, job_id),
        )
        connection.commit()


def get_job_stats(db_path: str | Path) -> dict:
    stats: dict[str, dict[str, int]] = {"pipeline_status": {}, "user_status": {}, "sponsor_status": {}}
    with _connect(db_path) as connection:
        for column in stats:
            rows = connection.execute(
                f"SELECT {column} AS value, COUNT(*) AS count FROM jobs GROUP BY {column}"
            ).fetchall()
            stats[column] = {row["value"] or "": row["count"] for row in rows}
        stats["total"] = connection.execute("SELECT COUNT(*) AS count FROM jobs").fetchone()["count"]
    return stats


def get_distinct_fetched_dates(db_path: str | Path) -> list[str]:
    with _connect(db_path) as connection:
        rows = connection.execute(
            "SELECT DISTINCT fetched_date FROM jobs WHERE fetched_date IS NOT NULL ORDER BY fetched_date DESC"
        ).fetchall()
    return [row["fetched_date"] for row in rows]


def get_latest_fetch_date(db_path: str | Path) -> str | None:
    with _connect(db_path) as connection:
        row = connection.execute("SELECT MAX(fetched_date) AS fetched_date FROM jobs").fetchone()
    return row["fetched_date"] if row and row["fetched_date"] else None
