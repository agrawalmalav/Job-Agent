from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from .storage import get_jobs
from .utils import ensure_dir


EXPORT_COLUMNS = [
    "id",
    "title",
    "company_name",
    "location",
    "posted_at",
    "fetched_date",
    "employment_type",
    "seniority_level",
    "workplace_type",
    "salary",
    "min_salary",
    "max_salary",
    "currency_code",
    "pay_period",
    "sponsor_status",
    "sponsor_confidence",
    "sponsor_matched_by",
    "sponsor_matched_name",
    "sponsor_matched_rows",
    "pipeline_status",
    "rejection_reason",
    "matched_rejection_keywords",
    "user_status",
    "user_notes",
    "apply_url",
    "linkedin_url",
    "created_at",
    "updated_at",
]


def export_jobs_csv(db_path: str, output_dir: str, filters: dict | None = None, name: str = "jobs") -> str:
    directory = ensure_dir(output_dir)
    today = date.today().isoformat()
    rows = get_jobs(db_path, filters)
    df = pd.DataFrame(rows).reindex(columns=EXPORT_COLUMNS)
    output_path = Path(directory) / f"{name}_{today}.csv"
    df.to_csv(output_path, index=False)
    return str(output_path)


def export_standard_csvs(db_path: str, output_dir: str) -> dict[str, str]:
    return {
        "all": export_jobs_csv(db_path, output_dir, name="all_jobs"),
        "accepted": export_jobs_csv(db_path, output_dir, {"pipeline_status": "accepted"}, "accepted_jobs"),
        "manual_review": export_jobs_csv(
            db_path,
            output_dir,
            {"pipeline_status": "manual_review"},
            "manual_review_jobs",
        ),
        "rejected": export_jobs_csv(db_path, output_dir, {"pipeline_status": "rejected"}, "rejected_jobs"),
        "applied": export_jobs_csv(db_path, output_dir, {"user_status": "applied"}, "applied_jobs"),
        "referral_requested": export_jobs_csv(
            db_path,
            output_dir,
            {"user_status": "referral_requested"},
            "referral_requested_jobs",
        ),
    }
