from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

import yaml

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

COMMON_WORDS = {
    "limited",
    "ltd",
    "plc",
    "llp",
    "inc",
    "corp",
    "corporation",
    "company",
    "co",
    "group",
    "holdings",
    "uk",
    "united",
    "kingdom",
    "technologies",
    "technology",
    "solutions",
    "services",
    "consulting",
    "consultancy",
    "international",
    "global",
    "the",
    "and",
    "of",
}


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


def _tokens(value: str) -> list[str]:
    raw_tokens = re.findall(r"[a-z0-9]+", _normalize_text(value))
    return [
        token
        for token in raw_tokens
        if token not in COMMON_WORDS and len(token) >= 3
    ]


def _row_to_text(row: dict[str, Any]) -> str:
    return json.dumps(row, ensure_ascii=True, sort_keys=True)


def _term_matches_name(term: str, sponsor_name: str) -> bool:
    normalized = _normalize_text(term)
    if not normalized:
        return False
    return normalized in _normalize_text(sponsor_name)


def _normalize_text(value: str) -> str:
    normalized = value.lower().replace("&", " and ")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _find_matches(search_terms: list[str], sponsor_rows: list[dict]) -> tuple[list[str], list[str], list[str]]:
    matched_names: list[str] = []
    matched_rows: list[str] = []
    matched_terms: list[str] = []
    for row in sponsor_rows:
        sponsor_name = _sponsor_name(row)
        row_terms = [term for term in search_terms if _term_matches_name(term, sponsor_name)]
        if row_terms:
            matched_names.append(sponsor_name)
            matched_rows.append(_row_to_text(row))
            matched_terms.extend(row_terms)
    return matched_names, matched_rows, list(dict.fromkeys(matched_terms))


def _alias_terms(company_name: str, aliases: dict) -> list[str]:
    company_lower = _normalize_text(company_name)
    terms: list[str] = []
    for alias_key, alias_values in aliases.items():
        alias_key_lower = _normalize_text(alias_key)
        if company_lower == alias_key_lower or alias_key_lower in company_lower:
            terms.extend(alias_values)
    return list(dict.fromkeys(terms))


def _confidence(search_terms: list[str], matched_by: str) -> str:
    if matched_by == "alias":
        return "high"
    if len(search_terms) >= 2:
        return "high"
    if search_terms and len(search_terms[0]) >= 5:
        return "high"
    if search_terms:
        return "medium"
    return "low"


def check_company_sponsor(company_name: str, sponsor_rows: list[dict], aliases: dict) -> SponsorResult:
    direct_terms = _tokens(company_name)
    matched_names, matched_rows, matched_terms = _find_matches(direct_terms, sponsor_rows)
    if matched_rows:
        confidence = _confidence(matched_terms, "direct")
        return SponsorResult(
            status="found" if confidence == "high" else "possible",
            confidence=confidence,
            matched_by="direct",
            search_terms=direct_terms,
            matched_name=matched_names[0],
            matched_rows=matched_rows,
        )

    alias_terms = _alias_terms(company_name, aliases)
    matched_names, matched_rows, _matched_terms = _find_matches(alias_terms, sponsor_rows)
    if matched_rows:
        return SponsorResult(
            status="found",
            confidence="high",
            matched_by="alias",
            search_terms=alias_terms,
            matched_name=matched_names[0],
            matched_rows=matched_rows,
        )

    return SponsorResult(
        status="not_found",
        confidence="low",
        matched_by="none",
        search_terms=direct_terms + alias_terms,
        matched_name=None,
        matched_rows=[],
    )
