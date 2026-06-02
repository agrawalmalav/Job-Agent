import sqlite3

from src.models import BasicFilterResult, Job, SponsorResult
from src.storage import (
    get_jobs,
    init_db,
    insert_job,
    job_exists,
    update_pipeline_status,
    update_pipeline_result,
    update_user_status,
    upsert_agency_company,
    is_agency_company,
    apply_agency_status_to_jobs,
    upsert_sponsor_override,
    get_sponsor_override,
    apply_sponsor_override_to_jobs,
)


def make_job(
    apify_id="1",
    linkedin_url="https://linkedin.com/jobs/view/1",
    apply_url="https://apply.example/1",
    company_name="Example",
    title="Software Engineer",
    location="London",
):
    return Job(
        source="test",
        apify_id=apify_id,
        title=title,
        standardized_title=None,
        company_name=company_name,
        country=None,
        location=location,
        posted_at=None,
        posted_at_timestamp=None,
        expire_at=None,
        employment_type="Full-time",
        seniority_level=None,
        job_function=None,
        industries=None,
        description_text=None,
        apply_method=None,
        apply_url=apply_url,
        linkedin_url=linkedin_url,
        applicants_count=None,
        salary=None,
        min_salary=None,
        max_salary=None,
        currency_code=None,
        pay_period=None,
        work_remote_allowed=None,
        workplace_type=None,
        company_linkedin_url=None,
        raw={},
    )


def sponsor(status="found"):
    return SponsorResult(status=status, confidence="high", matched_by="direct")


def filter_result():
    return BasicFilterResult(False, None, None, {})


def test_init_db_migrates_old_db_safely(tmp_path):
    db_path = tmp_path / "jobs.sqlite"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE jobs (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, status TEXT)"
        )
        connection.execute("INSERT INTO jobs (title, status) VALUES ('Role', 'accepted')")
        connection.commit()

    init_db(db_path)
    rows = get_jobs(db_path)

    assert rows[0]["pipeline_status"] == "accepted"
    assert rows[0]["user_status"] == "pending"


def test_insert_job_sets_user_status_pending(tmp_path):
    db_path = tmp_path / "jobs.sqlite"
    init_db(db_path)

    assert insert_job(db_path, make_job(), sponsor(), filter_result(), "accepted", 20) is True
    rows = get_jobs(db_path)

    assert rows[0]["pipeline_status"] == "accepted"
    assert rows[0]["user_status"] == "pending"


def test_duplicate_does_not_overwrite_user_status(tmp_path):
    db_path = tmp_path / "jobs.sqlite"
    init_db(db_path)

    insert_job(db_path, make_job(), sponsor(), filter_result(), "accepted", 20)
    job_id = get_jobs(db_path)[0]["id"]
    update_user_status(db_path, job_id, "applied", "Applied on company site")

    duplicate_inserted = insert_job(
        db_path,
        make_job(apify_id="different", linkedin_url="https://linkedin.com/jobs/view/1", apply_url="https://new.example"),
        sponsor(status="not_found"),
        filter_result(),
        "manual_review",
        5,
    )
    rows = get_jobs(db_path)

    assert duplicate_inserted is False
    assert len(rows) == 1
    assert rows[0]["user_status"] == "applied"
    assert rows[0]["user_notes"] == "Applied on company site"


def test_update_user_status_applied_sets_applied_at(tmp_path):
    db_path = tmp_path / "jobs.sqlite"
    init_db(db_path)
    insert_job(db_path, make_job(), sponsor(), filter_result(), "accepted", 20)
    job_id = get_jobs(db_path)[0]["id"]

    update_user_status(db_path, job_id, "applied")
    row = get_jobs(db_path)[0]

    assert row["user_status"] == "applied"
    assert row["applied_at"] is not None


def test_get_jobs_filters_by_pipeline_status_and_user_status(tmp_path):
    db_path = tmp_path / "jobs.sqlite"
    init_db(db_path)
    insert_job(db_path, make_job(apify_id="1", linkedin_url="l1", apply_url="a1"), sponsor(), filter_result(), "accepted", 20)
    insert_job(
        db_path,
        make_job(apify_id="2", linkedin_url="l2", apply_url="a2", title="Other Role"),
        sponsor(status="not_found"),
        filter_result(),
        "manual_review",
        5,
    )
    accepted_id = get_jobs(db_path, {"pipeline_status": "accepted"})[0]["id"]
    update_user_status(db_path, accepted_id, "applied")

    rows = get_jobs(db_path, {"pipeline_status": "accepted", "user_status": "applied"})

    assert len(rows) == 1
    assert rows[0]["pipeline_status"] == "accepted"
    assert rows[0]["user_status"] == "applied"


def test_get_jobs_filters_by_location_search(tmp_path):
    db_path = tmp_path / "jobs.sqlite"
    init_db(db_path)
    insert_job(
        db_path,
        make_job(apify_id="1", linkedin_url="l1", apply_url="a1", location="London"),
        sponsor(),
        filter_result(),
        "accepted",
        20,
    )
    insert_job(
        db_path,
        make_job(apify_id="2", linkedin_url="l2", apply_url="a2", location="Manchester"),
        sponsor(),
        filter_result(),
        "accepted",
        20,
    )

    rows = get_jobs(db_path, {"location_search": "lond"})

    assert len(rows) == 1
    assert rows[0]["location"] == "London"


def test_update_pipeline_status(tmp_path):
    db_path = tmp_path / "jobs.sqlite"
    init_db(db_path)
    insert_job(db_path, make_job(), sponsor(), filter_result(), "manual_review", 5)
    job_id = get_jobs(db_path)[0]["id"]

    update_pipeline_status(db_path, job_id, "accepted")
    row = get_jobs(db_path)[0]

    assert row["pipeline_status"] == "accepted"
    assert row["status"] == "accepted"
    assert row["updated_at"] is not None


def test_update_pipeline_result_does_not_overwrite_user_status(tmp_path):
    db_path = tmp_path / "jobs.sqlite"
    init_db(db_path)
    insert_job(db_path, make_job(), sponsor(status="not_found"), filter_result(), "manual_review", 5)
    job_id = get_jobs(db_path)[0]["id"]
    update_user_status(db_path, job_id, "applied", "already applied")

    rejection = BasicFilterResult(True, "basic_filter", "Rejected in test", {"test": ["keyword"]})
    update_pipeline_result(
        db_path,
        job_id,
        SponsorResult(status="not_found", confidence="low", matched_by="none"),
        rejection,
        "rejected",
        0,
    )
    row = get_jobs(db_path)[0]

    assert row["pipeline_status"] == "rejected"
    assert row["rejection_reason"] == "Rejected in test"
    assert row["user_status"] == "applied"
    assert row["user_notes"] == "already applied"


def test_agency_company_updates_matching_jobs_without_user_status(tmp_path):
    db_path = tmp_path / "jobs.sqlite"
    init_db(db_path)
    insert_job(db_path, make_job(company_name="Harnham"), sponsor(status="not_found"), filter_result(), "manual_review", 5)
    insert_job(
        db_path,
        make_job(apify_id="2", linkedin_url="l2", apply_url="a2", company_name="Harnham Ltd"),
        sponsor(status="not_found"),
        filter_result(),
        "manual_review",
        5,
    )
    first_id = get_jobs(db_path)[0]["id"]
    update_user_status(db_path, first_id, "applied", "do not touch")

    upsert_agency_company(db_path, "Harnham", added_by="test")
    updated_count = apply_agency_status_to_jobs(db_path, "Harnham")
    rows = get_jobs(db_path)

    assert is_agency_company(db_path, "Harnham Ltd") is True
    assert updated_count == 2
    assert {row["sponsor_status"] for row in rows} == {"agency"}
    assert get_jobs(db_path, {"user_status": "applied"})[0]["user_notes"] == "do not touch"


def test_sponsor_override_updates_matching_jobs_without_user_status(tmp_path):
    db_path = tmp_path / "jobs.sqlite"
    init_db(db_path)
    insert_job(db_path, make_job(company_name="Acme Software"), sponsor(status="not_found"), filter_result(), "manual_review", 5)
    insert_job(
        db_path,
        make_job(apify_id="2", linkedin_url="l2", apply_url="a2", company_name="Acme Software Ltd"),
        sponsor(status="not_found"),
        filter_result(),
        "manual_review",
        5,
    )
    first_id = get_jobs(db_path)[0]["id"]
    update_user_status(db_path, first_id, "referral_requested", "keep this")

    upsert_sponsor_override(db_path, "Acme Software", "self_confirmed", added_by="test")
    updated_count = apply_sponsor_override_to_jobs(db_path, "Acme Software", "self_confirmed")
    rows = get_jobs(db_path)

    assert get_sponsor_override(db_path, "Acme Software Ltd")["sponsor_status"] == "self_confirmed"
    assert updated_count == 2
    assert {row["sponsor_status"] for row in rows} == {"self_confirmed"}
    assert {row["pipeline_status"] for row in rows} == {"accepted"}
    assert get_jobs(db_path, {"user_status": "referral_requested"})[0]["user_notes"] == "keep this"


def test_sponsor_override_self_rejected_sets_manual_review(tmp_path):
    db_path = tmp_path / "jobs.sqlite"
    init_db(db_path)
    insert_job(db_path, make_job(company_name="Acme Software"), sponsor(status="found"), filter_result(), "accepted", 20)

    upsert_sponsor_override(db_path, "Acme Software", "self_rejected", added_by="test")
    apply_sponsor_override_to_jobs(db_path, "Acme Software", "self_rejected")
    row = get_jobs(db_path)[0]

    assert row["sponsor_status"] == "self_rejected"
    assert row["pipeline_status"] == "manual_review"
    assert row["rejection_reason"] == "Manually verified sponsorship unavailable"


def test_duplicate_detection_by_signature(tmp_path):
    db_path = tmp_path / "jobs.sqlite"
    init_db(db_path)
    insert_job(db_path, make_job(apify_id=None, linkedin_url=None, apply_url=None), sponsor(), filter_result(), "accepted", 20)

    duplicate = make_job(apify_id=None, linkedin_url=None, apply_url=None)

    assert job_exists(db_path, None, None, None, job=duplicate) is True
