from src.basic_filter import run_basic_filter
from src.models import Job


def make_job(**overrides):
    values = {
        "source": "test",
        "apify_id": "1",
        "title": "Software Engineer",
        "standardized_title": "Software Engineer",
        "company_name": "Example",
        "country": "United Kingdom",
        "location": "London",
        "posted_at": None,
        "posted_at_timestamp": None,
        "expire_at": None,
        "employment_type": "Full-time",
        "seniority_level": "Entry level",
        "job_function": "Engineering",
        "industries": "Software",
        "description_text": "Build Python services.",
        "apply_method": None,
        "apply_url": None,
        "linkedin_url": None,
        "applicants_count": None,
        "salary": None,
        "min_salary": None,
        "max_salary": None,
        "currency_code": None,
        "pay_period": None,
        "work_remote_allowed": None,
        "workplace_type": "Hybrid",
        "company_linkedin_url": None,
        "raw": {},
    }
    values.update(overrides)
    return Job(**values)


def config():
    return {
        "basic_filter": {
            "allowed_employment_types": ["full-time", "full time", "", "unspecified", "not specified"],
            "hard_reject_keywords": {
                "visa": ["no visa sponsorship"],
                "clearance": ["active sc clearance", "dv clearance"],
            },
            "contract_keywords": ["contract"],
            "role_type_negative_keywords": ["manual qa"],
            "seniority_negative_keywords": ["principal", "lead engineer", "tech lead"],
            "seniority_match_fields": ["title", "standardized_title", "seniority_level"],
        }
    }


def test_employment_type_full_time_passes():
    result = run_basic_filter(make_job(employment_type="Full-time"), config())
    assert result.hard_rejected is False


def test_employment_type_empty_passes():
    result = run_basic_filter(make_job(employment_type=""), config())
    assert result.hard_rejected is False


def test_employment_type_none_passes():
    result = run_basic_filter(make_job(employment_type=None), config())
    assert result.hard_rejected is False


def test_employment_type_contract_rejects():
    result = run_basic_filter(make_job(employment_type="Contract"), config())
    assert result.hard_rejected is True
    assert result.rejection_reason == "Rejected because employment type is not full-time or unspecified: Contract"


def test_visa_rejection_keyword():
    job = make_job(description_text="Unfortunately there is no visa sponsorship for this role.")
    result = run_basic_filter(job, config())

    assert result.hard_rejected is True
    assert result.rejection_stage == "basic_filter"
    assert result.matched_keywords["hard_reject_keywords.visa"] == ["no visa sponsorship"]


def test_clearance_rejection_keyword():
    job = make_job(description_text="This role requires active SC clearance.")
    result = run_basic_filter(job, config())

    assert result.hard_rejected is True
    assert result.matched_keywords["hard_reject_keywords.clearance"] == ["active sc clearance"]


def test_contract_rejection_keyword():
    job = make_job(description_text="This is a 6 month contract.", employment_type="Full-time")
    result = run_basic_filter(job, config())

    assert result.hard_rejected is True
    assert result.rejection_reason == "Rejected because contract keyword matched: contract"


def test_seniority_keyword_in_description_does_not_reject():
    job = make_job(title="Software Engineer", description_text="You will work with lead engineers.")
    result = run_basic_filter(job, config())

    assert result.hard_rejected is False


def test_seniority_keyword_in_title_rejects():
    job = make_job(title="Lead Engineer", standardized_title="Lead AI Engineer")
    result = run_basic_filter(job, config())

    assert result.hard_rejected is True
    assert result.matched_keywords["seniority_negative_keywords"] == ["lead engineer"]


def test_senior_software_engineer_does_not_reject():
    job = make_job(title="Senior Software Engineer", standardized_title="Senior Software Engineer")
    result = run_basic_filter(job, config())

    assert result.hard_rejected is False
