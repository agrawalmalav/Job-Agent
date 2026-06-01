from __future__ import annotations

import re


LEGAL_SUFFIXES = {
    "ltd",
    "limited",
    "llp",
    "plc",
    "inc",
    "incorporated",
    "corp",
    "corporation",
    "co",
    "company",
}

OPTIONAL_CORPORATE_WORDS = {
    "group",
    "holdings",
    "uk",
}

WEAK_GENERIC_WORDS = {
    "london",
    "partners",
    "partner",
    "global",
    "international",
    "solutions",
    "services",
    "consulting",
    "consultancy",
    "systems",
    "digital",
    "software",
    "technology",
    "technologies",
}


def _clean_name(name: str) -> str:
    cleaned = name.lower().replace("&", " and ")
    cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def normalize_company_name(name: str) -> str:
    cleaned = _clean_name(name or "")
    if not cleaned:
        return ""
    tokens = cleaned.split()
    filtered: list[str] = []
    index = 0
    while index < len(tokens):
        if index + 1 < len(tokens) and tokens[index] == "united" and tokens[index + 1] == "kingdom":
            index += 2
            continue
        token = tokens[index]
        if token in LEGAL_SUFFIXES or token in OPTIONAL_CORPORATE_WORDS:
            index += 1
            continue
        filtered.append(token)
        index += 1
    normalized = " ".join(filtered).strip()
    return normalized or cleaned


def extract_meaningful_tokens(company_name: str) -> list[str]:
    normalized = normalize_company_name(company_name)
    tokens = [
        token
        for token in normalized.split()
        if len(token) >= 3 and token not in LEGAL_SUFFIXES and token not in OPTIONAL_CORPORATE_WORDS
    ]
    return list(dict.fromkeys(tokens))


def extract_strong_tokens(company_name: str) -> list[str]:
    return [
        token
        for token in extract_meaningful_tokens(company_name)
        if token not in WEAK_GENERIC_WORDS
    ]
