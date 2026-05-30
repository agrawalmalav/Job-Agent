from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
import yaml

if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.config_loader import load_config
from src.main import resolve_path, run_pipeline
from src.models import PIPELINE_STATUSES, USER_STATUSES
from src.report_generator import export_jobs_csv, export_standard_csvs
from src.storage import (
    get_distinct_fetched_dates,
    get_job_stats,
    get_jobs,
    init_db,
    update_pipeline_status,
    update_user_status,
)


PROJECT_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_DIR / "config.yaml"

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
    "view",
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


def _choice(label: str, values: list[str], key: str, default: str = "All") -> str | None:
    options = [default] + values
    selected = st.sidebar.selectbox(label, options, key=key)
    return None if selected == default else selected


def _choice_with_default(label: str, values: list[str], key: str, selected_value: str) -> str | None:
    options = ["All"] + values
    index = options.index(selected_value) if selected_value in options else 0
    selected = st.sidebar.selectbox(label, options, index=index, key=key)
    return None if selected == "All" else selected


def _cell_value(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value)


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


def _render_detail(row: dict) -> None:
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
    c3.write(f"**Pipeline:** {row.get('pipeline_status') or ''}")
    c3.write(f"**User:** {row.get('user_status') or ''}")
    c3.write(f"**Sponsor:** {row.get('sponsor_status') or ''} ({row.get('sponsor_confidence') or ''})")

    link_cols = st.columns(2)
    if row.get("apply_url"):
        link_cols[0].link_button("Open Apply URL", row["apply_url"])
    if row.get("linkedin_url"):
        link_cols[1].link_button("Open LinkedIn URL", row["linkedin_url"])

    if row.get("rejection_reason"):
        st.warning(row["rejection_reason"])
    if row.get("sponsor_matched_name"):
        st.write(f"Company found on sponsor list: `{row['sponsor_matched_name']}`")
    if row.get("sponsor_matched_rows"):
        sponsor_matches = _sponsor_match_summary(row["sponsor_matched_rows"])
        if sponsor_matches.empty:
            st.caption("No readable sponsor match details found.")
        else:
            st.write("Possible sponsor-list matches")
            st.dataframe(sponsor_matches, use_container_width=True, hide_index=True)
    if row.get("description_text"):
        st.text_area("Description", row["description_text"], height=220, disabled=True)


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

    original_by_id = {int(row["id"]): row for row in rows}
    table_df = pd.DataFrame(rows).reindex(columns=[column for column in TABLE_COLUMNS if column != "view"])
    table_df.insert(0, "view", False)

    edited_df = st.data_editor(
        table_df,
        use_container_width=True,
        hide_index=True,
        height=520,
        column_config={
            "view": st.column_config.CheckboxColumn("View", help="Tick one row to show details below."),
            "pipeline_status": st.column_config.SelectboxColumn("Pipeline", options=PIPELINE_STATUSES),
            "user_status": st.column_config.SelectboxColumn("User", options=USER_STATUSES),
            "user_notes": st.column_config.TextColumn("Notes"),
            "apply_url": st.column_config.LinkColumn("Apply URL"),
            "linkedin_url": st.column_config.LinkColumn("LinkedIn URL"),
        },
        disabled=[
            column
            for column in TABLE_COLUMNS
            if column not in {"view", "pipeline_status", "user_status", "user_notes"}
        ],
        key="jobs_editor",
    )

    button_cols = st.columns([1, 4])
    if button_cols[0].button("Save table changes", type="primary"):
        changed = 0
        for edited_row in edited_df.to_dict("records"):
            job_id = int(edited_row["id"])
            original = original_by_id[job_id]
            pipeline_status = _cell_value(edited_row.get("pipeline_status")) or "manual_review"
            user_status = _cell_value(edited_row.get("user_status")) or "pending"
            notes = _cell_value(edited_row.get("user_notes"))

            pipeline_changed = pipeline_status != (original.get("pipeline_status") or "")
            user_changed = user_status != (original.get("user_status") or "pending")
            notes_changed = notes != (original.get("user_notes") or "")

            if pipeline_changed:
                update_pipeline_status(db_path, job_id, pipeline_status)
                changed += 1
            if user_changed or notes_changed:
                update_user_status(db_path, job_id, user_status, notes)
                changed += 1

        st.success(f"Saved {changed} change{'s' if changed != 1 else ''}.")
        st.rerun()

    selected_rows = edited_df[edited_df["view"] == True]
    if selected_rows.empty:
        st.info("Tick `View` on a row to see full details, links, sponsor row details, and description.")
    else:
        selected_job_id = int(selected_rows.iloc[-1]["id"])
        selected_row = original_by_id[selected_job_id]
        _render_detail(selected_row)


def settings_page(config: dict, aliases_path: str) -> None:
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
    st.set_page_config(page_title="Job Search Agent", layout="wide")
    config, db_path, reports_dir, aliases_path = _paths()

    st.title("Job Search Agent")
    st.caption("Local SQLite-backed job tracking dashboard.")

    tab_jobs, tab_settings, tab_run, tab_exports = st.tabs(
        ["Jobs", "Settings", "Run Pipeline", "Exports / Reports"]
    )
    with tab_jobs:
        jobs_page(db_path)
    with tab_settings:
        settings_page(config, aliases_path)
    with tab_run:
        run_pipeline_page()
    with tab_exports:
        exports_page(db_path, reports_dir)


if __name__ == "__main__":
    main()
