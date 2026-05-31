from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
import yaml
from dotenv import load_dotenv

if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.auth import login_required, logout_button
from src.config_loader import load_config
from src.main import resolve_path, run_pipeline
from src.models import PIPELINE_STATUSES, USER_STATUSES
from src.report_generator import export_jobs_csv, export_standard_csvs
from src.sponsor_checker import load_sponsor_list
from src.storage_router import (
    get_distinct_fetched_dates,
    get_job_stats,
    get_jobs,
    init_db,
    update_pipeline_status,
    update_user_status,
)


PROJECT_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_DIR / "config.yaml"
load_dotenv(PROJECT_DIR / ".env")

JOB_COLUMNS = [
    "id",
    "title",
    "company_name",
    "location",
    "posted_at",
    "fetched_date",
    "employment_type",
    "seniority_level",
    "workplace_type",
    "sponsor_status",
    "sponsor_confidence",
    "sponsor_matched_name",
    "pipeline_status",
    "rejection_reason",
    "user_status",
    "apply_url",
    "linkedin_url",
]

TABLE_COLUMNS = [
    "id",
    "title",
    "company_name",
    "location",
    "posted_at",
    "fetched_date",
    "employment_type",
    "workplace_type",
    "sponsor_status",
    "sponsor_confidence",
    "pipeline_status",
    "user_status",
    "user_notes",
    "apply_url",
    "linkedin_url",
]


def _paths() -> tuple[dict, str, str, str]:
    config = load_config(CONFIG_PATH)
    paths = config.get("paths", {})
    db_path = resolve_path(PROJECT_DIR, paths.get("sqlite_db", "data/jobs.sqlite"))
    reports_dir = resolve_path(PROJECT_DIR, paths.get("reports_dir", "reports"))
    aliases_path = resolve_path(PROJECT_DIR, paths.get("company_aliases", "data/company_aliases.yaml"))
    init_db(db_path)
    return config, db_path, reports_dir, aliases_path


def _storage_backend() -> str:
    return os.getenv("STORAGE_BACKEND", "sqlite").lower()


def _config_backend() -> str:
    return os.getenv("CONFIG_BACKEND", "local").lower()


def _dashboard_caption() -> str:
    if _storage_backend() == "supabase":
        return "Supabase-backed hosted job tracking dashboard."
    return "SQLite-backed local job tracking dashboard."


def _choice(label: str, values: list[str], key: str, default: str = "All") -> str | None:
    options = [default] + values
    selected = st.sidebar.selectbox(label, options, key=key)
    return None if selected == default else selected


def _choice_with_default(label: str, values: list[str], key: str, selected_value: str) -> str | None:
    options = ["All"] + values
    index = options.index(selected_value) if selected_value in options else 0
    selected = st.sidebar.selectbox(label, options, index=index, key=key)
    return None if selected == "All" else selected


def _sponsor_match_summary(matched_rows: str | None) -> pd.DataFrame:
    if not matched_rows:
        return pd.DataFrame(columns=["Company", "Location"])
    try:
        rows = json.loads(matched_rows)
    except json.JSONDecodeError:
        return pd.DataFrame(columns=["Company", "Location"])

    summaries: list[dict[str, str]] = []
    for row_text in rows:
        try:
            row = json.loads(row_text) if isinstance(row_text, str) else row_text
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        company = (
            row.get("Organisation Name")
            or row.get("organisation name")
            or row.get("organisation_name")
            or row.get("Company")
            or row.get("company")
            or row.get("Sponsor Name")
            or row.get("sponsor_name")
            or ""
        )
        location = (
            row.get("Town/City")
            or row.get("Town")
            or row.get("City")
            or row.get("County")
            or row.get("Location")
            or ""
        )
        summaries.append({"Company": company, "Location": location})
    return pd.DataFrame(summaries).drop_duplicates()


def _sponsor_display_rows(rows: list[dict]) -> pd.DataFrame:
    display_rows = []
    for row in rows:
        display_rows.append(
            {
                "Company": row.get("Organisation Name") or row.get("organisation_name") or "",
                "Town/City": row.get("Town/City") or row.get("town_city") or "",
                "County": row.get("County") or row.get("county") or "",
                "Type & Rating": row.get("Type & Rating") or row.get("type_rating") or "",
                "Route": row.get("Route") or row.get("route") or "",
            }
        )
    return pd.DataFrame(display_rows)


def _render_detail(row: dict, db_path: str) -> None:
    st.subheader("Selected Job Details")
    title = row.get("title") or "Untitled role"
    company = row.get("company_name") or "Unknown company"
    st.markdown(f"### {title}")
    st.caption(company)

    c1, c2, c3 = st.columns(3)
    c1.write(f"**Location:** {row.get('location') or ''}")
    c1.write(f"**Posted:** {row.get('posted_at') or ''}")
    c1.write(f"**Fetched:** {row.get('fetched_date') or ''}")
    c2.write(f"**Employment:** {row.get('employment_type') or ''}")
    c2.write(f"**Seniority:** {row.get('seniority_level') or ''}")
    c2.write(f"**Workplace:** {row.get('workplace_type') or ''}")

    current_pipeline_status = row.get("pipeline_status") or "manual_review"
    current_user_status = row.get("user_status") or "pending"
    selected_pipeline_status = c3.selectbox(
        "Pipeline status",
        PIPELINE_STATUSES,
        index=PIPELINE_STATUSES.index(current_pipeline_status)
        if current_pipeline_status in PIPELINE_STATUSES
        else 0,
        key=f"dialog_pipeline_{row['id']}",
    )
    selected_user_status = c3.selectbox(
        "User status",
        USER_STATUSES,
        index=USER_STATUSES.index(current_user_status) if current_user_status in USER_STATUSES else 0,
        key=f"dialog_user_{row['id']}",
    )
    c3.write(f"**Sponsor:** {row.get('sponsor_status') or ''} ({row.get('sponsor_confidence') or ''})")

    link_cols = st.columns(2)
    if row.get("apply_url"):
        link_cols[0].link_button("Open Apply URL", row["apply_url"])
    if row.get("linkedin_url"):
        link_cols[1].link_button("Open LinkedIn URL", row["linkedin_url"])

    if row.get("rejection_reason"):
        st.warning(row["rejection_reason"])

    if row.get("description_text"):
        st.markdown("#### Job Description")
        st.text_area("Description", row["description_text"], height=340, disabled=True, label_visibility="collapsed")

    notes = st.text_area(
        "Notes",
        value=row.get("user_notes") or "",
        height=110,
        key=f"dialog_notes_{row['id']}",
    )

    if row.get("sponsor_matched_name"):
        st.markdown("#### Sponsor Match")
        st.write(f"Company found on sponsor list: `{row['sponsor_matched_name']}`")
    if row.get("sponsor_matched_rows"):
        sponsor_matches = _sponsor_match_summary(row["sponsor_matched_rows"])
        if sponsor_matches.empty:
            st.caption("No readable sponsor match details found.")
        else:
            st.write("Possible sponsor-list matches")
            st.dataframe(sponsor_matches, use_container_width=True, hide_index=True)

    changed = False
    if selected_pipeline_status != current_pipeline_status:
        update_pipeline_status(db_path, row["id"], selected_pipeline_status)
        changed = True
    if selected_user_status != current_user_status or notes != (row.get("user_notes") or ""):
        update_user_status(db_path, row["id"], selected_user_status, notes)
        changed = True
    if changed:
        st.success("Autosaved.")
        st.rerun()


@st.dialog("Job Details", width="large")
def _job_detail_dialog(row: dict, db_path: str) -> None:
    _render_detail(row, db_path)


def jobs_page(db_path: str) -> None:
    st.header("Jobs")
    dates = get_distinct_fetched_dates(db_path)

    st.sidebar.header("Filters")
    fetched_date = _choice("Fetched date", dates, "fetched_date")
    pipeline_status = _choice_with_default("Pipeline status", PIPELINE_STATUSES[:-1], "pipeline_status", "accepted")
    user_status_options = ["pending", "All"] + [status for status in USER_STATUSES if status != "pending"]
    user_status_selection = st.sidebar.selectbox("User status", user_status_options, key="user_status")
    user_status = None if user_status_selection == "All" else user_status_selection
    sponsor_status = _choice("Sponsor status", ["found", "possible", "not_found"], "sponsor_status")
    company_search = st.sidebar.text_input("Company search")
    location_search = st.sidebar.text_input("Location search")
    keyword = st.sidebar.text_input("Keyword search")
    posted_date = st.sidebar.text_input("Posted date contains")
    workplace_type = st.sidebar.text_input("Workplace type")

    filters = {
        "fetched_date": fetched_date,
        "pipeline_status": pipeline_status,
        "user_status": user_status,
        "sponsor_status": sponsor_status,
        "company_search": company_search.strip() or None,
        "location_search": location_search.strip() or None,
        "keyword": keyword.strip() or None,
        "posted_date": posted_date.strip() or None,
        "workplace_type": workplace_type.strip() or None,
    }
    filters = {key: value for key, value in filters.items() if value}
    rows = get_jobs(db_path, filters)

    stats = get_job_stats(db_path)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total", stats.get("total", 0))
    c2.metric("Pending", stats.get("user_status", {}).get("pending", 0))
    c3.metric("Applied", stats.get("user_status", {}).get("applied", 0))
    c4.metric("Showing", len(rows))

    if not rows:
        st.info("No jobs match the current filters.")
        return

    table_df = pd.DataFrame(rows).reindex(columns=TABLE_COLUMNS)
    table_event = st.dataframe(
        table_df,
        use_container_width=True,
        hide_index=True,
        height=520,
        column_config={
            "apply_url": st.column_config.LinkColumn("Apply URL"),
            "linkedin_url": st.column_config.LinkColumn("LinkedIn URL"),
        },
        selection_mode="single-row",
        on_select="rerun",
        key="jobs_table",
    )
    st.caption("Click a row to open its details and update statuses.")

    selected_rows = table_event.selection.rows
    if selected_rows:
        selected_row = rows[selected_rows[0]]
        _job_detail_dialog(selected_row, db_path)


def _search_sponsors_supabase(query: str) -> list[dict]:
    from src.supabase_client import get_supabase_client

    response = (
        get_supabase_client()
        .table("sponsor_companies")
        .select("organisation_name,town_city,county,type_rating,route")
        .ilike("organisation_name", f"%{query}%")
        .order("organisation_name")
        .limit(250)
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


def sponsor_search_page(config: dict) -> None:
    st.header("Manual Sponsorship Check")
    st.caption("Search by substring in the sponsor organisation name, for example `wood`.")
    query = st.text_input("Company name contains")
    if not query.strip():
        st.info("Enter part of a company name to search the sponsor list.")
        return

    query_text = query.strip()
    try:
        if _storage_backend() == "supabase" or _config_backend() == "supabase":
            matches = _search_sponsors_supabase(query_text)
        else:
            sponsor_path = resolve_path(PROJECT_DIR, config.get("paths", {}).get("sponsor_csv", "data/sponsor_list.csv"))
            rows = load_sponsor_list(sponsor_path)
            query_lower = query_text.lower()
            matches = [
                row
                for row in rows
                if query_lower in str(row.get("Organisation Name") or "").lower()
            ][:250]
    except Exception as exc:
        st.error(f"Sponsor search failed: {exc}")
        return

    st.write(f"{len(matches)} match{'es' if len(matches) != 1 else ''} shown")
    if matches:
        st.dataframe(_sponsor_display_rows(matches), use_container_width=True, hide_index=True)
    else:
        st.info("No sponsor-list matches found.")


def _load_supabase_settings() -> dict:
    from src.supabase_client import get_supabase_client

    response = (
        get_supabase_client()
        .table("settings")
        .select("key,value_json")
        .in_("key", ["apify_config", "linkedin_search_urls", "basic_filter"])
        .execute()
    )
    rows = getattr(response, "data", None) or []
    return {row["key"]: row.get("value_json") for row in rows}


def _save_supabase_setting(key: str, value: object) -> None:
    from src.supabase_client import get_supabase_client

    get_supabase_client().table("settings").upsert(
        {"key": key, "value_json": value},
        on_conflict="key",
    ).execute()


def _load_supabase_alias_rows() -> list[dict]:
    from src.supabase_client import get_supabase_client

    response = (
        get_supabase_client()
        .table("company_aliases")
        .select("id,brand_name,alias_name,created_at")
        .order("brand_name")
        .execute()
    )
    return getattr(response, "data", None) or []


def _settings_page_supabase() -> None:
    st.header("Settings")
    st.caption("Settings are loaded from the Supabase `settings` table.")
    try:
        settings = _load_supabase_settings()
    except Exception as exc:
        st.error(f"Could not load Supabase settings: {exc}")
        return

    for key, default_value, height in (
        ("apify_config", {}, 180),
        ("linkedin_search_urls", [], 160),
        ("basic_filter", {}, 420),
    ):
        text = yaml.safe_dump(settings.get(key) or default_value, sort_keys=False)
        edited = st.text_area(key, text, height=height, key=f"setting_{key}")
        if st.button(f"Save {key}", key=f"save_{key}"):
            try:
                parsed = yaml.safe_load(edited)
            except yaml.YAMLError as exc:
                st.error(f"Invalid YAML for {key}: {exc}")
            else:
                _save_supabase_setting(key, parsed)
                st.success(f"{key} saved.")

    st.subheader("Company aliases")
    try:
        alias_rows = _load_supabase_alias_rows()
    except Exception as exc:
        st.error(f"Could not load Supabase aliases: {exc}")
    else:
        if alias_rows:
            st.dataframe(pd.DataFrame(alias_rows), use_container_width=True, hide_index=True)
        else:
            st.info("No aliases found in Supabase.")


def settings_page(config: dict, aliases_path: str) -> None:
    if _config_backend() == "supabase":
        _settings_page_supabase()
        return

    st.header("Settings")
    st.caption("Settings are saved to local YAML files. Invalid YAML is rejected before writing.")

    config_text = CONFIG_PATH.read_text(encoding="utf-8")
    edited_config = st.text_area("config.yaml", config_text, height=420)
    if st.button("Save config.yaml"):
        try:
            yaml.safe_load(edited_config)
        except yaml.YAMLError as exc:
            st.error(f"Invalid config YAML: {exc}")
        else:
            CONFIG_PATH.write_text(edited_config, encoding="utf-8")
            st.success("config.yaml saved.")

    alias_file = Path(aliases_path)
    aliases_text = alias_file.read_text(encoding="utf-8") if alias_file.exists() else "aliases:\n"
    edited_aliases = st.text_area("company_aliases.yaml", aliases_text, height=300)
    if st.button("Save company_aliases.yaml"):
        try:
            yaml.safe_load(edited_aliases)
        except yaml.YAMLError as exc:
            st.error(f"Invalid aliases YAML: {exc}")
        else:
            alias_file.write_text(edited_aliases, encoding="utf-8")
            st.success("company_aliases.yaml saved.")


def run_pipeline_page() -> None:
    st.header("Run Pipeline")
    st.write("Trigger the local Apify fetch/filter/store pipeline.")
    no_fetch = st.checkbox("Use latest raw JSON instead of fetching", value=False)
    debug_limit_enabled = st.checkbox("Debug limit raw jobs processed", value=False)
    debug_limit = None
    if debug_limit_enabled:
        debug_limit = st.number_input("Debug limit", min_value=1, step=1, value=15)

    if st.button("Run job fetch pipeline now", type="primary"):
        with st.spinner("Running pipeline..."):
            try:
                summary = run_pipeline(str(CONFIG_PATH), no_fetch=no_fetch, debug_limit=debug_limit)
            except Exception as exc:
                st.error(f"Pipeline failed: {exc}")
            else:
                st.success("Pipeline complete.")
                st.json(summary)


def exports_page(db_path: str, reports_dir: str) -> None:
    st.header("Exports / Reports")
    if st.button("Generate standard CSV exports"):
        paths = export_standard_csvs(db_path, reports_dir)
        st.success("Exports generated.")
        st.json(paths)

    st.subheader("Custom export")
    pipeline_status = st.selectbox("Pipeline status", ["All"] + PIPELINE_STATUSES[:-1])
    user_status = st.selectbox("User status", ["All"] + USER_STATUSES)
    filters = {}
    if pipeline_status != "All":
        filters["pipeline_status"] = pipeline_status
    if user_status != "All":
        filters["user_status"] = user_status
    if st.button("Export current selection"):
        path = export_jobs_csv(db_path, reports_dir, filters, "custom_jobs")
        st.success(f"Exported: {path}")


def main() -> None:
    st.set_page_config(page_title="Job Search Agent", layout="wide", initial_sidebar_state="collapsed")
    login_required()
    logout_button()

    config, db_path, reports_dir, aliases_path = _paths()

    st.title("Job Search Agent")
    st.caption(_dashboard_caption())

    tab_jobs, tab_sponsor, tab_settings, tab_run, tab_exports = st.tabs(
        ["Jobs", "Sponsor Search", "Settings", "Run Pipeline", "Exports / Reports"]
    )
    with tab_jobs:
        jobs_page(db_path)
    with tab_sponsor:
        sponsor_search_page(config)
    with tab_settings:
        settings_page(config, aliases_path)
    with tab_run:
        run_pipeline_page()
    with tab_exports:
        exports_page(db_path, reports_dir)


if __name__ == "__main__":
    main()
