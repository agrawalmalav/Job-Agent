from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


DEFAULT_PATHS = {
    "sqlite_db": "data/jobs.sqlite",
    "raw_dir": "data/raw",
    "reports_dir": "reports",
    "sponsor_csv": "data/2026-05-22_sponsor_list.csv",
    "company_aliases": "data/company_aliases.yaml",
}


def _config_backend() -> str:
    import os

    return os.getenv("CONFIG_BACKEND", "local").lower()


def load_config_from_supabase() -> dict[str, Any]:
    from .supabase_client import get_supabase_client

    response = (
        get_supabase_client()
        .table("settings")
        .select("key,value_json")
        .in_("key", ["apify_config", "linkedin_search_urls", "basic_filter", "sponsorship_description_match"])
        .execute()
    )
    rows = getattr(response, "data", None) or []
    settings = {row["key"]: row.get("value_json") for row in rows}
    return {
        "apify": settings.get("apify_config") or {},
        "linkedin_search_urls": settings.get("linkedin_search_urls") or [],
        "paths": DEFAULT_PATHS.copy(),
        "basic_filter": settings.get("basic_filter") or {},
        "sponsorship_description_match": settings.get("sponsorship_description_match") or {},
    }


def load_config(config_path: str | Path = "config.yaml") -> dict[str, Any]:
    if _config_backend() == "supabase":
        return load_config_from_supabase()
    with Path(config_path).open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file) or {}
    return config
