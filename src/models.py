from __future__ import annotations

from dataclasses import dataclass, field


PIPELINE_STATUSES = ["accepted", "manual_review", "rejected", "duplicate"]
USER_STATUSES = [
    "pending",
    "applied",
    "rejected",
    "referral_requested",
    "interview_scheduled",
    "closed",
]


@dataclass
class Job:
    source: str
    apify_id: str | None
    title: str
    standardized_title: str | None
    company_name: str
    country: str | None
    location: str | None
    posted_at: str | None
    posted_at_timestamp: str | None
    expire_at: str | None
    employment_type: str | None
    seniority_level: str | None
    job_function: str | None
    industries: str | None
    description_text: str | None
    apply_method: str | None
    apply_url: str | None
    linkedin_url: str | None
    applicants_count: str | None
    salary: str | None
    min_salary: str | None
    max_salary: str | None
    currency_code: str | None
    pay_period: str | None
    work_remote_allowed: str | None
    workplace_type: str | None
    company_linkedin_url: str | None
    raw: dict


@dataclass
class BasicFilterResult:
    hard_rejected: bool
    rejection_stage: str | None
    rejection_reason: str | None
    matched_keywords: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class SponsorResult:
    status: str
    confidence: str
    matched_by: str
    search_terms: list[str] = field(default_factory=list)
    matched_name: str | None = None
    matched_rows: list[str] = field(default_factory=list)
