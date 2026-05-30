from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from .utils import ensure_dir


def _get_run_value(run: object, key: str) -> object | None:
    if isinstance(run, dict):
        return run.get(key)

    model_dump = getattr(run, "model_dump", None)
    if callable(model_dump):
        data = model_dump(by_alias=True)
        if key in data:
            return data[key]
        snake_key = _camel_to_snake(key)
        return data.get(snake_key)

    if hasattr(run, key):
        return getattr(run, key)
    return getattr(run, _camel_to_snake(key), None)


def _camel_to_snake(value: str) -> str:
    chars: list[str] = []
    for char in value:
        if char.isupper():
            chars.append("_")
            chars.append(char.lower())
        else:
            chars.append(char)
    return "".join(chars).lstrip("_")


def fetch_jobs_from_apify(config: dict) -> list[dict]:
    token = os.getenv("APIFY_TOKEN")
    if not token:
        raise RuntimeError("APIFY_TOKEN is missing. Add it to .env before fetching.")

    try:
        from apify_client import ApifyClient
    except ImportError as exc:
        raise RuntimeError("apify-client is not installed. Run pip install -r requirements.txt.") from exc

    apify_config = config.get("apify", {})
    actor_input = {
        "urls": config.get("linkedin_search_urls", []),
        "scrapeCompany": apify_config.get("scrape_company", True),
        "count": apify_config.get("count", 100),
        "splitByLocation": apify_config.get("split_by_location", False),
    }

    actor_id = apify_config.get("actor_id", "curious_coder/linkedin-jobs-scraper")
    client = ApifyClient(token)
    run = client.actor(actor_id).call(run_input=actor_input)
    dataset_id = _get_run_value(run, "defaultDatasetId")
    if not dataset_id:
        return []

    dataset_items = client.dataset(dataset_id).list_items()
    return list(dataset_items.items)


def save_raw_jobs(raw_jobs: list[dict], raw_dir: str | Path) -> str:
    directory = ensure_dir(raw_dir)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = directory / f"jobs_{timestamp}.json"
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(raw_jobs, file, indent=2, ensure_ascii=False)
    return str(output_path)


def load_latest_raw_jobs(raw_dir: str | Path) -> list[dict]:
    directory = Path(raw_dir)
    files = sorted(directory.glob("jobs_*.json"))
    if not files:
        return []
    with files[-1].open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, list):
        raise ValueError(f"Latest raw jobs file is not a list: {files[-1]}")
    return data
