# Job Search Agent

A local-first Python MVP for UK job discovery and tracking. It fetches LinkedIn jobs via Apify, cleans useful fields, rejects obvious bad matches with configurable keywords, checks companies against your local sponsor-list CSV, stores everything in SQLite, and gives you a Streamlit dashboard for review.

It does not auto-apply, edit resumes, generate cover letters, use RAG, use a vector database, or use a cloud database.

## Setup

Requires Python 3.11+.

Windows PowerShell:

```powershell
cd F:\job_search_agent
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

macOS/Linux:

```bash
cd job_search_agent
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Add your Apify token to `.env`:

```text
APIFY_TOKEN=your_token_here
```

Using a virtual environment is recommended, but the app can still read `.env` without one.

## Run The Pipeline

Fetch from Apify, store new jobs, skip duplicates, and export CSVs:

```powershell
python -m src.main
```

Use the latest raw JSON file without fetching:

```powershell
python -m src.main --no-fetch
```

Debug only: limit raw jobs processed in one run:

```powershell
python -m src.main --limit 15
```

`--limit` is not a product cap. Stored jobs and dashboard results are not capped.

## Run The Dashboard

```powershell
streamlit run src/dashboard.py
```

The dashboard has tabs for:

- `Jobs`: filter jobs, open links, update `user_status`, and save notes.
- `Settings`: edit `config.yaml` and `data/company_aliases.yaml` safely with YAML validation.
- `Run Pipeline`: trigger the fetch/filter/store pipeline manually.
- `Exports / Reports`: generate CSV exports.

Default job view shows `pending` jobs. You can filter by fetched date, pipeline status, user status, sponsor status, company, keyword, employment type, and workplace type.

## LinkedIn Search URLs

Edit `config.yaml`:

```yaml
linkedin_search_urls:
  - "https://www.linkedin.com/jobs/search/..."
```

For full-time LinkedIn jobs, include `f_JT=F` in the search URL. The pipeline also filters results locally so only full-time or unspecified employment types pass.

Apify fetch volume is controlled by:

```yaml
apify:
  count: 100
```

## Sponsor CSV

Your current config points to:

```text
data/2026-05-22_sponsor_list.csv
```

Replace that file or update `paths.sponsor_csv` in `config.yaml` when you download a newer sponsor list. The CSV is assumed to already be filtered to useful routes such as Skilled Worker and Scale-up, so the code does not do route filtering.

Company appearing on the UK sponsor list does not guarantee sponsorship for a specific role.

## Company Aliases

Edit:

```text
data/company_aliases.yaml
```

Examples:

- `PwC` -> `PricewaterhouseCoopers`
- `EY` -> `Ernst & Young`
- `Admiral` -> `EUI`

## Rejection Keywords

Edit `config.yaml` under `basic_filter`.

The important pieces are:

- `allowed_employment_types`: only full-time or unspecified jobs pass.
- `hard_reject_keywords`: visa and clearance phrases.
- `contract_keywords`: contract terms.
- `role_type_negative_keywords`: unwanted role types.
- `seniority_negative_keywords`: checked only against title, standardized title, and seniority level.

`Senior Software Engineer` is not rejected by default. Terms like `principal`, `lead engineer`, `tech lead`, and `engineering manager` are rejected when they appear in title-like fields.

## Statuses

The database tracks two separate statuses.

`pipeline_status` is system-generated:

- `accepted`: passed basic filtering and company was found on the sponsor list.
- `manual_review`: passed basic filtering but sponsor match was possible or not found.
- `rejected`: rejected by the basic filter.
- `duplicate`: reserved for future run tracking; duplicates are currently skipped and not inserted.

`user_status` is set by you in the dashboard:

- `pending`
- `applied`
- `rejected`
- `referral_requested`
- `interview_scheduled`
- `closed`

Running the pipeline again does not overwrite `user_status` or notes for duplicates.

## Exports

CSV exports are written to `reports/`, including all jobs, accepted jobs, manual-review jobs, rejected jobs, applied jobs, and referral-requested jobs.

The Streamlit dashboard is the primary UI because it can update SQLite. Static HTML reports are no longer the main interface.

## Tests

```powershell
pytest
```

## Future Cloud Deployment Plan

The current version uses Streamlit and SQLite locally. The code is split so migration is easier later:

- Pipeline logic lives in `src/main.py` as `run_pipeline(...)`.
- Database operations are isolated in `src/storage.py`.
- Config handling is isolated in `src/config_loader.py`.
- UI code is isolated in `src/dashboard.py`.

A future hosted version could move `storage.py` to Supabase Postgres, rebuild the dashboard in Next.js/Vercel or Streamlit Community Cloud, expose manual pipeline runs through an authenticated API endpoint, and add scheduled daily runs using platform cron.
