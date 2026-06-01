from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

from .apify_fetcher import fetch_jobs_from_apify, load_latest_raw_jobs, save_raw_jobs
from .basic_filter import run_basic_filter
from .config_loader import load_config
from .field_cleaner import clean_apify_job
from .models import SponsorResult
from .report_generator import export_standard_csvs
from .sponsor_checker import (
    check_company_sponsor,
    load_company_aliases,
    load_company_aliases_from_supabase,
    load_sponsor_list,
    load_sponsor_list_from_supabase,
)
from .storage_router import get_job_stats, init_db, insert_job, job_exists
from .storage_router import find_duplicate_job, get_jobs, is_agency_company, update_pipeline_result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local UK job-search discovery pipeline.")
    parser.add_argument("--no-fetch", action="store_true", help="Use latest raw JSON instead of calling Apify.")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Debug only: limit raw jobs processed in this run.",
    )
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml.")
    return parser.parse_args()


def resolve_path(base_dir: Path, value: str) -> str:
    path = Path(value)
    return str(path if path.is_absolute() else base_dir / path)


def _decide_status_and_score(filter_result, sponsor_result: SponsorResult) -> tuple[str, int]:
    if filter_result.hard_rejected:
        return "rejected", 0
    if sponsor_result.status == "agency":
        return "manual_review", 5
    if sponsor_result.status == "found":
        return "accepted", 20
    if sponsor_result.status == "possible":
        return "manual_review", 10
    return "manual_review", 5


def _progress(message: str) -> None:
    print(message, flush=True)


def _job_from_db_row(row: dict):
    from .models import Job

    return Job(
        source=row.get("source") or "db",
        apify_id=row.get("apify_id"),
        title=row.get("title") or "",
        standardized_title=row.get("standardized_title"),
        company_name=row.get("company_name") or "",
        country=row.get("country"),
        location=row.get("location"),
        posted_at=row.get("posted_at"),
        posted_at_timestamp=row.get("posted_at_timestamp"),
        expire_at=row.get("expire_at"),
        employment_type=row.get("employment_type"),
        seniority_level=row.get("seniority_level"),
        job_function=row.get("job_function"),
        industries=row.get("industries"),
        description_text=row.get("description_text"),
        apply_method=row.get("apply_method"),
        apply_url=row.get("apply_url"),
        linkedin_url=row.get("linkedin_url"),
        applicants_count=row.get("applicants_count"),
        salary=row.get("salary"),
        min_salary=row.get("min_salary"),
        max_salary=row.get("max_salary"),
        currency_code=row.get("currency_code"),
        pay_period=row.get("pay_period"),
        work_remote_allowed=row.get("work_remote_allowed"),
        workplace_type=row.get("workplace_type"),
        company_linkedin_url=row.get("company_linkedin_url"),
        raw={},
    )


def _load_sponsor_sources(config: dict, project_dir: Path) -> tuple[list[dict], dict]:
    paths = config.get("paths", {})
    sponsor_csv = resolve_path(project_dir, paths.get("sponsor_csv", "data/sponsor_list.csv"))
    aliases_path = resolve_path(project_dir, paths.get("company_aliases", "data/company_aliases.yaml"))
    if os.getenv("CONFIG_BACKEND", "local").lower() == "supabase" or os.getenv("STORAGE_BACKEND", "sqlite").lower() == "supabase":
        _progress("Loading sponsor data and aliases from Supabase...")
        return load_sponsor_list_from_supabase(), load_company_aliases_from_supabase()

    _progress("Loading local sponsor data and aliases...")
    return load_sponsor_list(sponsor_csv), load_company_aliases(aliases_path)


def _evaluate_job(
    job,
    config: dict,
    sponsor_rows: list[dict],
    aliases: dict,
    db_path: str | None = None,
) -> tuple[SponsorResult, object, str, int]:
    filter_result = run_basic_filter(job, config)
    if filter_result.hard_rejected:
        sponsor_result = SponsorResult(status="not_found", confidence="low", matched_by="none")
    else:
        agency_checker = None
        if db_path is not None:
            agency_checker = lambda company_name: is_agency_company(db_path, company_name)
        sponsor_result = check_company_sponsor(job.company_name, sponsor_rows, aliases, agency_checker=agency_checker)
    pipeline_status, final_score = _decide_status_and_score(filter_result, sponsor_result)
    return sponsor_result, filter_result, pipeline_status, final_score


def reprocess_jobs(
    config_path: str = "config.yaml",
    scope: str = "latest_raw",
    debug_limit: int | None = None,
) -> dict:
    project_dir = Path(config_path).resolve().parent
    load_dotenv(project_dir / ".env")
    _progress("Loading config...")
    config = load_config(config_path)
    paths = config.get("paths", {})
    db_path = resolve_path(project_dir, paths.get("sqlite_db", "data/jobs.sqlite"))
    raw_dir = resolve_path(project_dir, paths.get("raw_dir", "data/raw"))
    reports_dir = resolve_path(project_dir, paths.get("reports_dir", "reports"))
    init_db(db_path)

    sponsor_rows, aliases = _load_sponsor_sources(config, project_dir)

    if scope == "all_db":
        _progress("Loading all jobs from database...")
        source_rows = get_jobs(db_path)
        if debug_limit is not None:
            source_rows = source_rows[:debug_limit]
        items = [(row.get("id"), _job_from_db_row(row)) for row in source_rows if row.get("id")]
    else:
        _progress("Loading latest raw jobs...")
        raw_jobs = load_latest_raw_jobs(raw_dir)
        if debug_limit is not None:
            raw_jobs = raw_jobs[:debug_limit]
        items = []
        for raw_job in raw_jobs:
            job = clean_apify_job(raw_job)
            duplicate = find_duplicate_job(db_path, job)
            if duplicate and duplicate.get("id"):
                items.append((duplicate["id"], job))

    _progress(f"Reprocessing {len(items)} jobs...")
    updated = 0
    for index, (job_id, job) in enumerate(items, start=1):
        sponsor_result, filter_result, pipeline_status, final_score = _evaluate_job(
            job,
            config,
            sponsor_rows,
            aliases,
            db_path=db_path,
        )
        update_pipeline_result(db_path, job_id, sponsor_result, filter_result, pipeline_status, final_score)
        updated += 1
        if index % 25 == 0 or index == len(items):
            _progress(f"Reprocessed {index}/{len(items)} jobs...")

    _progress("Exporting CSVs and calculating stats...")
    export_paths = export_standard_csvs(db_path, reports_dir)
    stats = get_job_stats(db_path)
    pipeline_counts = stats.get("pipeline_status", {})
    return {
        "scope": scope,
        "jobs_considered": len(items),
        "jobs_updated": updated,
        "accepted_count": pipeline_counts.get("accepted", 0),
        "manual_review_count": pipeline_counts.get("manual_review", 0),
        "rejected_count": pipeline_counts.get("rejected", 0),
        "export_paths": export_paths,
    }


def run_pipeline(
    config_path: str = "config.yaml",
    no_fetch: bool = False,
    debug_limit: int | None = None,
) -> dict:
    project_dir = Path(config_path).resolve().parent
    load_dotenv(project_dir / ".env")
    _progress("Loading config...")
    config = load_config(config_path)

    paths = config.get("paths", {})
    db_path = resolve_path(project_dir, paths.get("sqlite_db", "data/jobs.sqlite"))
    raw_dir = resolve_path(project_dir, paths.get("raw_dir", "data/raw"))
    reports_dir = resolve_path(project_dir, paths.get("reports_dir", "reports"))

    init_db(db_path)

    if no_fetch:
        _progress("Loading latest raw jobs...")
        raw_jobs = load_latest_raw_jobs(raw_dir)
        raw_path = "latest raw file"
    else:
        _progress("Fetching jobs from Apify...")
        raw_jobs = fetch_jobs_from_apify(config)
        raw_path = save_raw_jobs(raw_jobs, raw_dir)

    if debug_limit is not None:
        raw_jobs = raw_jobs[:debug_limit]

    sponsor_rows, aliases = _load_sponsor_sources(config, project_dir)

    _progress(f"Processing {len(raw_jobs)} jobs...")
    inserted = 0
    duplicates = 0
    for index, raw_job in enumerate(raw_jobs, start=1):
        job = clean_apify_job(raw_job)
        if job_exists(db_path, job.linkedin_url, job.apply_url, job.apify_id, job=job):
            duplicates += 1
            continue

        sponsor_result, filter_result, pipeline_status, final_score = _evaluate_job(
            job,
            config,
            sponsor_rows,
            aliases,
            db_path=db_path,
        )
        if insert_job(db_path, job, sponsor_result, filter_result, pipeline_status, final_score):
            inserted += 1
        else:
            duplicates += 1
        if index % 10 == 0 or index == len(raw_jobs):
            _progress(f"Processed {index}/{len(raw_jobs)} jobs...")

    _progress("Exporting CSVs and calculating stats...")
    export_paths = export_standard_csvs(db_path, reports_dir)
    stats = get_job_stats(db_path)
    pipeline_counts = stats.get("pipeline_status", {})
    user_counts = stats.get("user_status", {})

    return {
        "raw_source": raw_path,
        "raw_jobs_processed": len(raw_jobs),
        "inserted_jobs": inserted,
        "duplicates_skipped": duplicates,
        "accepted_count": pipeline_counts.get("accepted", 0),
        "manual_review_count": pipeline_counts.get("manual_review", 0),
        "rejected_count": pipeline_counts.get("rejected", 0),
        "pending_count": user_counts.get("pending", 0),
        "applied_count": user_counts.get("applied", 0),
        "referral_requested_count": user_counts.get("referral_requested", 0),
        "export_paths": export_paths,
        "dashboard_command": "streamlit run src/dashboard.py",
    }


def main() -> None:
    args = parse_args()
    summary = run_pipeline(args.config, no_fetch=args.no_fetch, debug_limit=args.limit)

    print("Job discovery run complete")
    print(f"Raw source: {summary['raw_source']}")
    print(f"Raw jobs processed: {summary['raw_jobs_processed']}")
    print(f"Inserted jobs: {summary['inserted_jobs']}")
    print(f"Duplicates skipped: {summary['duplicates_skipped']}")
    print(f"Accepted jobs: {summary['accepted_count']}")
    print(f"Manual review jobs: {summary['manual_review_count']}")
    print(f"Rejected jobs: {summary['rejected_count']}")
    print(f"Pending user status: {summary['pending_count']}")
    print(f"Applied user status: {summary['applied_count']}")
    print(f"Referral requested user status: {summary['referral_requested_count']}")
    print(f"Dashboard: {summary['dashboard_command']}")
    print("CSV exports:")
    for name, path in summary["export_paths"].items():
        print(f"  {name}: {path}")


if __name__ == "__main__":
    main()
