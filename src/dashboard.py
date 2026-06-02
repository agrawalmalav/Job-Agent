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
from src.main import reprocess_jobs, resolve_path, run_pipeline
from src.models import PIPELINE_STATUSES, USER_STATUSES
from src.report_generator import export_jobs_csv, export_standard_csvs
from src.sponsor_checker import load_sponsor_list
from src.storage_router import (
    apply_agency_status_to_jobs,
    apply_sponsor_override_to_jobs,
    delete_sponsor_override,
    get_distinct_fetched_dates,
    get_job_stats,
    get_jobs,
    init_db,
    upsert_agency_company,
    upsert_sponsor_override,
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
    "title",
    "company_name",
    "user_status",
    "pipeline_status",
    "sponsor_status",
    "apply_url",
    "linkedin_url",
    "location",
    "employment_type",
    "salary",
    "posted_at",
    "fetched_date",
    "workplace_type",
    "sponsor_confidence",
    "user_notes",
]

TABLE_COLUMN_LABELS = {
    "title": "Title",
    "company_name": "Company",
    "user_status": "Action",
    "pipeline_status": "Status",
    "sponsor_status": "Sponsor",
    "apply_url": "Apply",
    "linkedin_url": "LinkedIn",
    "location": "Location",
    "employment_type": "Employment",
    "salary": "Salary",
    "posted_at": "Posted",
    "fetched_date": "Fetched",
    "workplace_type": "Workplace",
    "sponsor_confidence": "Sponsor Confidence",
    "user_notes": "Notes",
}


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


def _list_to_text(values: list | None) -> str:
    return "\n".join(str(value) for value in (values or []))


def _text_to_list(value: str) -> list[str]:
    return [line.strip() for line in value.splitlines() if line.strip()]


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
    title = row.get("title") or "Untitled role"
    company = row.get("company_name") or "Unknown company"
    st.markdown(f"### {title}")
    st.markdown(f"### {company}")
    st.caption(f"Posted: {row.get('posted_at') or 'Unknown'} | Fetched: {row.get('fetched_date') or 'Unknown'}")

    c1, c2, c3 = st.columns(3)
    c1.write(f"**Location:** {row.get('location') or ''}")
    c2.write(f"**Employment:** {row.get('employment_type') or ''}")
    c2.write(f"**Seniority:** {row.get('seniority_level') or ''}")
    c2.write(f"**Workplace:** {row.get('workplace_type') or ''}")

    current_pipeline_status = row.get("pipeline_status") or "manual_review"
    current_user_status = row.get("user_status") or "pending"
    current_sponsor_status = row.get("sponsor_status") or "not_found"
    manual_sponsor_options = {
        "Agency": "agency",
        "Self confirmed": "self_confirmed",
        "Self rejected": "self_rejected",
    }
    sponsor_label_by_status = {value: label for label, value in manual_sponsor_options.items()}
    if current_sponsor_status in sponsor_label_by_status:
        sponsor_options = list(manual_sponsor_options)
        sponsor_index = sponsor_options.index(sponsor_label_by_status[current_sponsor_status])
    else:
        auto_label = f"Auto: {current_sponsor_status}"
        sponsor_options = [auto_label, *manual_sponsor_options]
        sponsor_index = 0
    selected_sponsor_label = c3.selectbox(
        "Sponsor",
        sponsor_options,
        index=sponsor_index,
        key=f"dialog_sponsor_{row['id']}",
    )
    selected_pipeline_status = c3.selectbox(
        "Status",
        PIPELINE_STATUSES,
        index=PIPELINE_STATUSES.index(current_pipeline_status)
        if current_pipeline_status in PIPELINE_STATUSES
        else 0,
        key=f"dialog_pipeline_{row['id']}",
    )
    selected_user_status = c3.selectbox(
        "Action",
        USER_STATUSES,
        index=USER_STATUSES.index(current_user_status) if current_user_status in USER_STATUSES else 0,
        key=f"dialog_user_{row['id']}",
    )
    c3.caption(f"Confidence: {row.get('sponsor_confidence') or 'unknown'}")
    if current_sponsor_status == "agency":
        c3.warning("Agency / actual employer unknown")
    elif current_sponsor_status == "self_confirmed":
        c3.success("Self confirmed sponsor")
    elif current_sponsor_status == "self_rejected":
        c3.warning("Self rejected sponsor")

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
    selected_manual_sponsor_status = manual_sponsor_options.get(selected_sponsor_label)
    if selected_manual_sponsor_status and selected_manual_sponsor_status != current_sponsor_status:
        if selected_manual_sponsor_status == "agency":
            delete_sponsor_override(db_path, company)
            upsert_agency_company(
                db_path,
                company,
                notes="Marked from dashboard",
                added_by=st.session_state.get("username"),
            )
            updated_count = apply_agency_status_to_jobs(db_path, company)
            st.success(f"Marked {company} as agency and updated {updated_count} existing jobs.")
        else:
            upsert_sponsor_override(
                db_path,
                company,
                selected_manual_sponsor_status,
                notes="Marked from dashboard",
                added_by=st.session_state.get("username"),
            )
            updated_count = apply_sponsor_override_to_jobs(db_path, company, selected_manual_sponsor_status)
            label = selected_sponsor_label.lower()
            st.success(f"Marked {company} as {label} and updated {updated_count} existing jobs.")
        st.rerun()

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
    pipeline_status = _choice_with_default("Status", PIPELINE_STATUSES[:-1], "pipeline_status", "accepted")
    user_status_options = ["pending", "All"] + [status for status in USER_STATUSES if status != "pending"]
    user_status_selection = st.sidebar.selectbox("Action", user_status_options, key="user_status")
    user_status = None if user_status_selection == "All" else user_status_selection
    sponsor_status = _choice(
        "Sponsor status",
        ["found", "possible", "not_found", "agency", "self_confirmed", "self_rejected"],
        "sponsor_status",
    )
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
    c2.metric("Pending Action", stats.get("user_status", {}).get("pending", 0))
    c3.metric("Applied", stats.get("user_status", {}).get("applied", 0))
    c4.metric("Showing", len(rows))

    if not rows:
        st.info("No jobs match the current filters.")
        return

    table_df = pd.DataFrame(rows).reindex(columns=TABLE_COLUMNS).rename(columns=TABLE_COLUMN_LABELS)
    table_event = st.dataframe(
        table_df,
        use_container_width=True,
        hide_index=True,
        height=520,
        column_config={
            "Title": st.column_config.TextColumn("Title", width="large", pinned=True),
            "Company": st.column_config.TextColumn("Company", width="medium", pinned=True),
            "Action": st.column_config.TextColumn("Action", width="small"),
            "Status": st.column_config.TextColumn("Status", width="small"),
            "Sponsor": st.column_config.TextColumn("Sponsor", width="small"),
            "Apply": st.column_config.LinkColumn("Apply", width="small", display_text="Apply", max_chars=12),
            "LinkedIn": st.column_config.LinkColumn("LinkedIn", width="small", display_text="LinkedIn", max_chars=12),
            "Location": st.column_config.TextColumn("Location", width="medium"),
            "Notes": st.column_config.TextColumn("Notes", width="medium"),
        },
        selection_mode="single-row",
        on_select="rerun",
        key="jobs_table",
    )
    st.caption("Click a row to open its details and update status/action.")

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
        .in_("key", ["apify_config", "linkedin_search_urls", "basic_filter", "sponsorship_description_match"])
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

    config = {
        "apify": settings.get("apify_config") or {},
        "linkedin_search_urls": settings.get("linkedin_search_urls") or [],
        "basic_filter": settings.get("basic_filter") or {},
        "sponsorship_description_match": settings.get("sponsorship_description_match") or {},
        "paths": {},
    }
    updated = _config_form(config, show_paths=False)
    if updated:
        _save_supabase_setting("apify_config", updated.get("apify", {}))
        _save_supabase_setting("linkedin_search_urls", updated.get("linkedin_search_urls", []))
        _save_supabase_setting("basic_filter", updated.get("basic_filter", {}))
        _save_supabase_setting(
            "sponsorship_description_match",
            updated.get("sponsorship_description_match", {}),
        )
        st.success("Supabase settings saved.")

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
    st.caption("Settings are saved to local config.yaml.")

    updated = _config_form(config, show_paths=True)
    if updated:
        CONFIG_PATH.write_text(yaml.safe_dump(updated, sort_keys=False), encoding="utf-8")
        st.success("config.yaml saved.")

    with st.expander("Advanced YAML editor"):
        config_text = CONFIG_PATH.read_text(encoding="utf-8")
        edited_config = st.text_area("config.yaml", config_text, height=420)
        if st.button("Save raw config.yaml"):
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


def _config_form(config: dict, show_paths: bool) -> dict | None:
    apify = config.get("apify", {})
    basic_filter = config.get("basic_filter", {})
    hard_reject = basic_filter.get("hard_reject_keywords", {})
    description_match = config.get("sponsorship_description_match", {})

    with st.form("config_form"):
        st.subheader("Apify")
        actor_id = st.text_input("Actor ID", value=apify.get("actor_id", "curious_coder/linkedin-jobs-scraper"))
        count = st.number_input("Apify count", min_value=1, max_value=1000, value=int(apify.get("count", 100)))
        scrape_company = st.checkbox("Scrape company", value=bool(apify.get("scrape_company", True)))
        split_by_location = st.checkbox("Split by location", value=bool(apify.get("split_by_location", False)))

        st.subheader("LinkedIn Search URLs")
        urls_text = st.text_area("One URL per line", value=_list_to_text(config.get("linkedin_search_urls", [])), height=150)

        paths = config.get("paths", {}).copy()
        if show_paths:
            st.subheader("Paths")
            paths["sponsor_csv"] = st.text_input("Sponsor CSV", value=paths.get("sponsor_csv", "data/2026-05-22_sponsor_list.csv"))
            paths["company_aliases"] = st.text_input("Company aliases YAML", value=paths.get("company_aliases", "data/company_aliases.yaml"))
            paths["sqlite_db"] = st.text_input("SQLite DB", value=paths.get("sqlite_db", "data/jobs.sqlite"))
            paths["raw_dir"] = st.text_input("Raw jobs directory", value=paths.get("raw_dir", "data/raw"))
            paths["reports_dir"] = st.text_input("Reports directory", value=paths.get("reports_dir", "reports"))

        st.subheader("Basic Filter")
        allowed_employment_types = st.text_area(
            "Allowed employment types",
            value=_list_to_text(basic_filter.get("allowed_employment_types", [])),
            height=120,
        )
        visa_keywords = st.text_area("Visa hard-reject keywords", value=_list_to_text(hard_reject.get("visa", [])), height=150)
        clearance_keywords = st.text_area(
            "Clearance hard-reject keywords",
            value=_list_to_text(hard_reject.get("clearance", [])),
            height=120,
        )
        contract_keywords = st.text_area(
            "Contract keywords",
            value=_list_to_text(basic_filter.get("contract_keywords", [])),
            height=120,
        )
        role_type_negative_keywords = st.text_area(
            "Role type negative keywords",
            value=_list_to_text(basic_filter.get("role_type_negative_keywords", [])),
            height=160,
        )
        seniority_negative_keywords = st.text_area(
            "Seniority negative keywords",
            value=_list_to_text(basic_filter.get("seniority_negative_keywords", [])),
            height=150,
        )
        seniority_match_fields = st.text_area(
            "Seniority match fields",
            value=_list_to_text(basic_filter.get("seniority_match_fields", ["title", "standardized_title", "seniority_level"])),
            height=90,
        )
        positive_sponsorship_patterns = st.text_area(
            "Positive sponsorship description patterns",
            value=_list_to_text(description_match.get("positive_patterns", [])),
            height=150,
            help="One case-insensitive regex pattern per line. Plain phrases also work.",
        )
        negative_sponsorship_patterns = st.text_area(
            "Negative sponsorship guard patterns",
            value=_list_to_text(description_match.get("negative_patterns", [])),
            height=130,
            help="If any of these patterns match, the positive description match is ignored.",
        )

        submitted = st.form_submit_button("Save settings", type="primary")
    if not submitted:
        return None

    updated_hard_reject = dict(hard_reject)
    updated_hard_reject["visa"] = _text_to_list(visa_keywords)
    updated_hard_reject["clearance"] = _text_to_list(clearance_keywords)
    updated_config = dict(config)
    updated_config["apify"] = {
        "actor_id": actor_id,
        "count": int(count),
        "scrape_company": scrape_company,
        "split_by_location": split_by_location,
    }
    updated_config["linkedin_search_urls"] = _text_to_list(urls_text)
    if show_paths:
        updated_config["paths"] = paths
    updated_config["basic_filter"] = {
        **basic_filter,
        "allowed_employment_types": _text_to_list(allowed_employment_types),
        "hard_reject_keywords": updated_hard_reject,
        "contract_keywords": _text_to_list(contract_keywords),
        "role_type_negative_keywords": _text_to_list(role_type_negative_keywords),
        "seniority_negative_keywords": _text_to_list(seniority_negative_keywords),
        "seniority_match_fields": _text_to_list(seniority_match_fields),
    }
    updated_config["sponsorship_description_match"] = {
        **description_match,
        "positive_patterns": _text_to_list(positive_sponsorship_patterns),
        "negative_patterns": _text_to_list(negative_sponsorship_patterns),
    }
    return updated_config


def run_pipeline_page() -> None:
    st.header("Run Pipeline")
    st.write("Choose whether to fetch new jobs or only recalculate classifications after settings/list changes.")
    mode = st.radio(
        "Pipeline action",
        [
            "Fetch new jobs from Apify",
            "Process latest saved Apify raw file as new jobs",
            "Recalculate matching jobs from latest saved raw file",
            "Recalculate every job already in the database",
        ],
    )
    mode_help = {
        "Fetch new jobs from Apify": "Calls Apify, saves the raw response, inserts only new jobs, and classifies them.",
        "Process latest saved Apify raw file as new jobs": "Does not call Apify. Uses the newest JSON in data/raw and inserts only new jobs.",
        "Recalculate matching jobs from latest saved raw file": "Does not insert new jobs. Updates existing matching jobs using current config, agency list, sponsor overrides, aliases, and sponsor list.",
        "Recalculate every job already in the database": "Does not use Apify or raw files. Re-runs classification for all stored jobs while preserving action and notes.",
    }
    st.caption(mode_help[mode])
    debug_limit_enabled = st.checkbox("Debug limit raw jobs processed", value=False)
    debug_limit = None
    if debug_limit_enabled:
        debug_limit = st.number_input("Debug limit", min_value=1, step=1, value=15)

    if mode in {
        "Recalculate matching jobs from latest saved raw file",
        "Recalculate every job already in the database",
    }:
        st.info("Manual sponsor values such as agency, self confirmed, and self rejected are preserved through their company lists. Action and notes are not changed.")

    if st.button("Run selected pipeline action", type="primary"):
        with st.spinner("Running pipeline..."):
            try:
                if mode == "Fetch new jobs from Apify":
                    summary = run_pipeline(str(CONFIG_PATH), no_fetch=False, debug_limit=debug_limit)
                elif mode == "Process latest saved Apify raw file as new jobs":
                    summary = run_pipeline(str(CONFIG_PATH), no_fetch=True, debug_limit=debug_limit)
                elif mode == "Recalculate matching jobs from latest saved raw file":
                    summary = reprocess_jobs(str(CONFIG_PATH), scope="latest_raw", debug_limit=debug_limit)
                else:
                    summary = reprocess_jobs(str(CONFIG_PATH), scope="all_db", debug_limit=debug_limit)
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
    pipeline_status = st.selectbox("Status", ["All"] + PIPELINE_STATUSES[:-1])
    user_status = st.selectbox("Action", ["All"] + USER_STATUSES)
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
