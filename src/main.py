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
    if sponsor_result.status == "found":
        return "accepted", 20
    if sponsor_result.status == "possible":
        return "manual_review", 10
    return "manual_review", 5


def _progress(message: str) -> None:
    print(message, flush=True)


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
    sponsor_csv = resolve_path(project_dir, paths.get("sponsor_csv", "data/sponsor_list.csv"))
    aliases_path = resolve_path(project_dir, paths.get("company_aliases", "data/company_aliases.yaml"))
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

    if os.getenv("CONFIG_BACKEND", "local").lower() == "supabase" or os.getenv("STORAGE_BACKEND", "sqlite").lower() == "supabase":
        _progress("Loading sponsor data and aliases from Supabase...")
        sponsor_rows = load_sponsor_list_from_supabase()
        aliases = load_company_aliases_from_supabase()
    else:
        _progress("Loading local sponsor data and aliases...")
        sponsor_rows = load_sponsor_list(sponsor_csv)
        aliases = load_company_aliases(aliases_path)

    _progress(f"Processing {len(raw_jobs)} jobs...")
    inserted = 0
    duplicates = 0
    for index, raw_job in enumerate(raw_jobs, start=1):
        job = clean_apify_job(raw_job)
        if job_exists(db_path, job.linkedin_url, job.apply_url, job.apify_id, job=job):
            duplicates += 1
            continue

        filter_result = run_basic_filter(job, config)
        if filter_result.hard_rejected:
            sponsor_result = SponsorResult(status="not_found", confidence="low", matched_by="none")
        else:
            sponsor_result = check_company_sponsor(job.company_name, sponsor_rows, aliases)

        pipeline_status, final_score = _decide_status_and_score(filter_result, sponsor_result)
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
