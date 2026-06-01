from __future__ import annotations

import os


def _backend():
    if os.getenv("STORAGE_BACKEND", "sqlite").lower() == "supabase":
        from . import supabase_storage as storage_backend
    else:
        from . import storage as storage_backend
    return storage_backend


def init_db(db_path=None):
    return _backend().init_db(db_path)


def insert_job(db_path, job, sponsor_result, filter_result, pipeline_status, final_score):
    return _backend().insert_job(db_path, job, sponsor_result, filter_result, pipeline_status, final_score)


def job_exists(db_path, linkedin_url, apply_url, apify_id, job=None):
    return _backend().job_exists(db_path, linkedin_url, apply_url, apify_id, job=job)


def find_duplicate_job(db_path, job):
    return _backend().find_duplicate_job(db_path, job)


def get_jobs(db_path, filters=None):
    return _backend().get_jobs(db_path, filters)


def get_jobs_by_date(db_path, fetched_date, status=None):
    return _backend().get_jobs_by_date(db_path, fetched_date, status)


def update_user_status(db_path, job_id, user_status, notes=None):
    return _backend().update_user_status(db_path, job_id, user_status, notes)


def update_user_notes(db_path, job_id, notes):
    return _backend().update_user_notes(db_path, job_id, notes)


def update_pipeline_status(db_path, job_id, pipeline_status):
    return _backend().update_pipeline_status(db_path, job_id, pipeline_status)


def update_pipeline_result(db_path, job_id, sponsor_result, filter_result, pipeline_status, final_score):
    return _backend().update_pipeline_result(
        db_path,
        job_id,
        sponsor_result,
        filter_result,
        pipeline_status,
        final_score,
    )


def get_job_stats(db_path):
    return _backend().get_job_stats(db_path)


def get_distinct_fetched_dates(db_path):
    return _backend().get_distinct_fetched_dates(db_path)


def get_latest_fetch_date(db_path):
    return _backend().get_latest_fetch_date(db_path)


def get_agency_company(db_path, company_name):
    return _backend().get_agency_company(db_path, company_name)


def is_agency_company(db_path, company_name):
    return _backend().is_agency_company(db_path, company_name)


def upsert_agency_company(db_path, company_name, notes=None, added_by=None):
    return _backend().upsert_agency_company(db_path, company_name, notes, added_by)


def apply_agency_status_to_jobs(db_path, company_name):
    return _backend().apply_agency_status_to_jobs(db_path, company_name)
