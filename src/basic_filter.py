from __future__ import annotations

import re

from .models import BasicFilterResult, Job


SEARCH_FIELDS = (
    "title",
    "standardized_title",
    "company_name",
    "country",
    "location",
    "employment_type",
    "seniority_level",
    "job_function",
    "industries",
    "description_text",
    "salary",
    "workplace_type",
)


DEFAULT_ALLOWED_EMPLOYMENT_TYPES = {"full-time", "full time", "", "unspecified", "not specified"}


def _searchable_text(job: Job) -> str:
    parts = [getattr(job, field) for field in SEARCH_FIELDS]
    return " ".join(str(part) for part in parts if part).lower()


def _fields_text(job: Job, fields: list[str] | tuple[str, ...]) -> str:
    parts = [getattr(job, field, None) for field in fields]
    return " ".join(str(part) for part in parts if part).lower()


def _keyword_matches(text: str, keyword: str) -> bool:
    normalized = keyword.lower().strip()
    if not normalized:
        return False
    if re.fullmatch(r"\w+", normalized):
        return bool(re.search(rf"\b{re.escape(normalized)}\b", text, flags=re.IGNORECASE))
    return normalized in text


def _collect_matches(text: str, keywords: list[str]) -> list[str]:
    return [keyword for keyword in keywords if _keyword_matches(text, keyword)]


def _reject(reason: str, matched_keywords: dict[str, list[str]]) -> BasicFilterResult:
    return BasicFilterResult(
        hard_rejected=True,
        rejection_stage="basic_filter",
        rejection_reason=reason,
        matched_keywords=matched_keywords,
    )


def run_basic_filter(job: Job, config: dict) -> BasicFilterResult:
    text = _searchable_text(job)
    filter_config = config.get("basic_filter", {})
    matched_keywords: dict[str, list[str]] = {}
    employment_type = (job.employment_type or "").strip()
    allowed_employment_types = {
        str(value).lower().strip()
        for value in filter_config.get("allowed_employment_types", DEFAULT_ALLOWED_EMPLOYMENT_TYPES)
    }
    if employment_type.lower() not in allowed_employment_types:
        matched_keywords["employment_type"] = [employment_type]
        return _reject(
            f"Rejected because employment type is not full-time or unspecified: {employment_type}",
            matched_keywords,
        )

    for category, keywords in filter_config.get("hard_reject_keywords", {}).items():
        matches = _collect_matches(text, keywords or [])
        if matches:
            key = f"hard_reject_keywords.{category}"
            matched_keywords[key] = matches
            return _reject(
                f"Rejected because {category} hard-reject keyword matched: {matches[0]}",
                matched_keywords,
            )

    contract_matches = _collect_matches(text, filter_config.get("contract_keywords", []) or [])
    if contract_matches:
        matched_keywords["contract_keywords"] = contract_matches
        return _reject(
            f"Rejected because contract keyword matched: {contract_matches[0]}",
            matched_keywords,
        )

    role_matches = _collect_matches(text, filter_config.get("role_type_negative_keywords", []) or [])
    if role_matches:
        matched_keywords["role_type_negative_keywords"] = role_matches
        return _reject(
            f"Rejected because role type negative keyword matched: {role_matches[0]}",
            matched_keywords,
        )

    seniority_fields = filter_config.get(
        "seniority_match_fields",
        ["title", "standardized_title", "seniority_level"],
    )
    seniority_text = _fields_text(job, seniority_fields)
    seniority_matches = _collect_matches(seniority_text, filter_config.get("seniority_negative_keywords", []) or [])
    if seniority_matches:
        matched_keywords["seniority_negative_keywords"] = seniority_matches
        return _reject(
            f"Rejected because seniority negative keyword matched: {seniority_matches[0]}",
            matched_keywords,
        )

    return BasicFilterResult(
        hard_rejected=False,
        rejection_stage=None,
        rejection_reason=None,
        matched_keywords={},
    )
