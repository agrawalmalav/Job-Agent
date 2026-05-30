from __future__ import annotations

from typing import Any

from .models import Job
from .utils import stringify


FIELD_MAP = {
    "applicants_count": "applicantsCount",
    "apply_method": "applyMethod",
    "apply_url": "applyUrl",
    "company_linkedin_url": "companyLinkedinUrl",
    "company_name": "companyName",
    "country": "country",
    "description_text": "descriptionText",
    "employment_type": "employmentType",
    "expire_at": "expireAt",
    "apify_id": "id",
    "industries": "industries",
    "job_function": "jobFunction",
    "linkedin_url": "link",
    "location": "location",
    "posted_at": "postedAt",
    "posted_at_timestamp": "postedAtTimestamp",
    "salary": "salary",
    "currency_code": "salaryInsights/compensationBreakdown/0/currencyCode",
    "max_salary": "salaryInsights/compensationBreakdown/0/maxSalary",
    "min_salary": "salaryInsights/compensationBreakdown/0/minSalary",
    "pay_period": "salaryInsights/compensationBreakdown/0/payPeriod",
    "seniority_level": "seniorityLevel",
    "standardized_title": "standardizedTitle",
    "title": "title",
    "work_remote_allowed": "workRemoteAllowed",
    "workplace_type": "workplaceTypes/0",
}


def _get_nested(raw: dict, path: str) -> Any:
    current: Any = raw
    for part in path.split("/"):
        if isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def clean_apify_job(raw: dict) -> Job:
    values = {
        field_name: stringify(_get_nested(raw, raw_path))
        for field_name, raw_path in FIELD_MAP.items()
    }
    return Job(
        source="apify_linkedin",
        apify_id=values["apify_id"],
        title=values["title"] or "",
        standardized_title=values["standardized_title"],
        company_name=values["company_name"] or "",
        country=values["country"],
        location=values["location"],
        posted_at=values["posted_at"],
        posted_at_timestamp=values["posted_at_timestamp"],
        expire_at=values["expire_at"],
        employment_type=values["employment_type"],
        seniority_level=values["seniority_level"],
        job_function=values["job_function"],
        industries=values["industries"],
        description_text=values["description_text"],
        apply_method=values["apply_method"],
        apply_url=values["apply_url"],
        linkedin_url=values["linkedin_url"],
        applicants_count=values["applicants_count"],
        salary=values["salary"],
        min_salary=values["min_salary"],
        max_salary=values["max_salary"],
        currency_code=values["currency_code"],
        pay_period=values["pay_period"],
        work_remote_allowed=values["work_remote_allowed"],
        workplace_type=values["workplace_type"],
        company_linkedin_url=values["company_linkedin_url"],
        raw=raw,
    )
