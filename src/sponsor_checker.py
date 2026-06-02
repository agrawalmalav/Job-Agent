from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

import yaml

from .company_utils import extract_meaningful_tokens, extract_strong_tokens, normalize_company_name
from .models import SponsorResult


LIKELY_NAME_COLUMNS = (
    "Organisation Name",
    "organisation name",
    "organisation_name",
    "Company",
    "company",
    "Sponsor Name",
    "sponsor_name",
)

DEFAULT_POSITIVE_SPONSORSHIP_PATTERNS = (
    r"\bvisa sponsorship (?:is )?available\b",
    r"\bsponsorship (?:is )?available\b",
    r"\bvisa sponsorship (?:is )?(?:offered|provided)\b",
    r"\bskilled worker visa sponsorship (?:is )?available\b",
    r"\bcertificate of sponsorship (?:is )?available\b",
    r"\bwe (?:can|are able to|will) sponsor\b",
    r"\bable to sponsor (?:a )?(?:visa|visas|skilled worker visa)\b",
)

DEFAULT_NEGATIVE_SPONSORSHIP_GUARDS = (
    r"\bno\b.{0,60}\bsponsorship\b",
    r"\bnot\b.{0,60}\bsponsorship\b",
    r"\bwithout\b.{0,60}\bsponsorship\b",
    r"\b(?:unable|cannot|can't)\b.{0,60}\bsponsor\b",
    r"\b(?:do not|does not|will not)\b.{0,60}\bsponsor\b",
)


def load_sponsor_list(csv_path: str | Path) -> list[dict]:
    path = Path(csv_path)
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def load_company_aliases(alias_path: str | Path) -> dict:
    path = Path(alias_path)
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    aliases = data.get("aliases", data)
    return {
        str(key).lower(): [str(value).lower() for value in values]
        for key, values in aliases.items()
    }


def load_sponsor_list_from_supabase() -> list[dict]:
    from .supabase_client import get_supabase_client

    response = (
        get_supabase_client()
        .table("sponsor_companies")
        .select("organisation_name,town_city,county,type_rating,route")
        .execute()
    )
    rows = getattr(response, "data", None) or []
    return [
        {
            "Organisation Name": row.get("organisation_name"),
            "Town/City": row.get("town_city"),
            "County": row.get("county"),
            "Type & Rating": row.get("type_rating"),
            "Route": row.get("route"),
        }
        for row in rows
    ]


def load_company_aliases_from_supabase() -> dict:
    from .supabase_client import get_supabase_client

    response = (
        get_supabase_client()
        .table("company_aliases")
        .select("brand_name,alias_name")
        .execute()
    )
    rows = getattr(response, "data", None) or []
    aliases: dict[str, list[str]] = {}
    for row in rows:
        brand_name = str(row.get("brand_name") or "").lower().strip()
        alias_name = str(row.get("alias_name") or "").lower().strip()
        if not brand_name or not alias_name:
            continue
        aliases.setdefault(brand_name, []).append(alias_name)
    return aliases


def _name_column(row: dict[str, Any]) -> str | None:
    for column in LIKELY_NAME_COLUMNS:
        if column in row:
            return column
    return next(iter(row.keys()), None)


def _sponsor_name(row: dict[str, Any]) -> str:
    column = _name_column(row)
    return str(row.get(column, "")) if column else ""


def _row_to_text(row: dict[str, Any]) -> str:
    return json.dumps(row, ensure_ascii=True, sort_keys=True)


def _normalize_text(value: str) -> str:
    normalized = value.lower().replace("&", " and ")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _search_configured_pattern(pattern: str, text: str) -> re.Match | None:
    try:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match
    except re.error:
        pass
    escaped = re.escape(pattern.lower())
    return re.search(escaped, text, flags=re.IGNORECASE)


def find_positive_sponsorship_phrase(
    description_text: str | None,
    positive_patterns: list[str] | tuple[str, ...] | None = None,
    negative_patterns: list[str] | tuple[str, ...] | None = None,
) -> str | None:
    if not description_text:
        return None
    positive_patterns = positive_patterns or DEFAULT_POSITIVE_SPONSORSHIP_PATTERNS
    negative_patterns = negative_patterns or DEFAULT_NEGATIVE_SPONSORSHIP_GUARDS
    text = re.sub(r"\s+", " ", description_text.lower())
    if any(_search_configured_pattern(pattern, text) for pattern in negative_patterns):
        return None
    for pattern in positive_patterns:
        match = _search_configured_pattern(pattern, text)
        if match:
            return match.group(0)
    return None


def _find_phrase_matches(search_terms: list[str], sponsor_rows: list[dict]) -> tuple[list[str], list[str], list[str]]:
    matched_names: list[str] = []
    matched_rows: list[str] = []
    matched_terms: list[str] = []
    for row in sponsor_rows:
        sponsor_name = _sponsor_name(row)
        normalized_sponsor = normalize_company_name(sponsor_name)
        row_terms = [
            term
            for term in search_terms
            if normalize_company_name(term) and normalize_company_name(term) in normalized_sponsor
        ]
        if row_terms:
            matched_names.append(sponsor_name)
            matched_rows.append(_row_to_text(row))
            matched_terms.extend(row_terms)
    return matched_names, matched_rows, list(dict.fromkeys(matched_terms))


def _find_exact_normalized_match(company_name: str, sponsor_rows: list[dict]) -> tuple[list[str], list[str]]:
    target = normalize_company_name(company_name)
    if not target:
        return [], []
    matched_names: list[str] = []
    matched_rows: list[str] = []
    for row in sponsor_rows:
        sponsor_name = _sponsor_name(row)
        if normalize_company_name(sponsor_name) == target:
            matched_names.append(sponsor_name)
            matched_rows.append(_row_to_text(row))
            if len(matched_rows) >= 10:
                break
    return matched_names, matched_rows


def _find_all_token_matches(tokens: list[str], sponsor_rows: list[dict]) -> tuple[list[str], list[str]]:
    matched_names: list[str] = []
    matched_rows: list[str] = []
    if not tokens:
        return matched_names, matched_rows
    for row in sponsor_rows:
        sponsor_name = _sponsor_name(row)
        normalized_sponsor = normalize_company_name(sponsor_name)
        if all(token in normalized_sponsor for token in tokens):
            matched_names.append(sponsor_name)
            matched_rows.append(_row_to_text(row))
            if len(matched_rows) >= 10:
                break
    return matched_names, matched_rows


def _count_all_token_matches(tokens: list[str], sponsor_rows: list[dict]) -> int:
    if not tokens:
        return 0
    count = 0
    for row in sponsor_rows:
        normalized_sponsor = normalize_company_name(_sponsor_name(row))
        if all(token in normalized_sponsor for token in tokens):
            count += 1
            if count > 10:
                break
    return count


def _alias_terms(company_name: str, aliases: dict) -> list[str]:
    company_lower = _normalize_text(company_name)
    terms: list[str] = []
    for alias_key, alias_values in aliases.items():
        alias_key_lower = _normalize_text(alias_key)
        if company_lower == alias_key_lower or alias_key_lower in company_lower:
            terms.extend(alias_values)
    return list(dict.fromkeys(terms))


def check_company_sponsor(
    company_name: str,
    sponsor_rows: list[dict],
    aliases: dict,
    agency_checker=None,
    sponsor_override_lookup=None,
) -> SponsorResult:
    normalized_company_name = normalize_company_name(company_name)
    if sponsor_override_lookup:
        override = sponsor_override_lookup(company_name)
        if override:
            sponsor_status = override.get("sponsor_status")
            if sponsor_status in {"self_confirmed", "self_rejected"}:
                return SponsorResult(
                    status=sponsor_status,
                    confidence="high",
                    matched_by="manual_sponsor",
                    search_terms=[normalized_company_name],
                    matched_name=override.get("company_name") or company_name,
                    matched_rows=[],
                )

    if agency_checker and agency_checker(company_name):
        return SponsorResult(
            status="agency",
            confidence="high",
            matched_by="agency_list",
            search_terms=[normalized_company_name],
            matched_name=company_name,
            matched_rows=[],
        )

    alias_terms = _alias_terms(company_name, aliases)
    matched_names, matched_rows, _matched_terms = _find_phrase_matches(alias_terms, sponsor_rows)
    if matched_rows:
        return SponsorResult(
            status="found",
            confidence="high",
            matched_by="alias",
            search_terms=alias_terms,
            matched_name=matched_names[0],
            matched_rows=matched_rows,
        )

    matched_names, matched_rows = _find_exact_normalized_match(company_name, sponsor_rows)
    if matched_rows:
        return SponsorResult(
            status="found",
            confidence="high",
            matched_by="direct",
            search_terms=[normalized_company_name],
            matched_name=matched_names[0],
            matched_rows=matched_rows,
        )

    meaningful_tokens = extract_meaningful_tokens(company_name)
    strong_tokens = extract_strong_tokens(company_name)
    search_terms = strong_tokens or meaningful_tokens
    if len(strong_tokens) >= 2:
        total_matches = _count_all_token_matches(strong_tokens, sponsor_rows)
        matched_names, matched_rows = _find_all_token_matches(strong_tokens, sponsor_rows)
        if matched_rows:
            return SponsorResult(
                status="possible" if total_matches > 10 else "found",
                confidence="low" if total_matches > 10 else "high",
                matched_by="direct_tokens",
                search_terms=strong_tokens,
                matched_name=matched_names[0],
                matched_rows=matched_rows,
            )
    elif len(strong_tokens) == 1 and len(strong_tokens[0]) >= 4:
        total_matches = _count_all_token_matches(strong_tokens, sponsor_rows)
        matched_names, matched_rows = _find_all_token_matches(strong_tokens, sponsor_rows)
        if matched_rows:
            return SponsorResult(
                status="possible" if total_matches > 10 else "found",
                confidence="low" if total_matches > 10 else "high",
                matched_by="direct_token",
                search_terms=strong_tokens,
                matched_name=matched_names[0],
                matched_rows=matched_rows,
            )

    return SponsorResult(
        status="not_found",
        confidence="low",
        matched_by="none",
        search_terms=search_terms + alias_terms,
        matched_name=None,
        matched_rows=[],
    )
