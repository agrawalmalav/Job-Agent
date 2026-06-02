# Job Search Agent

A local-first Python MVP for UK job discovery and tracking. It fetches LinkedIn jobs via Apify, cleans useful fields, rejects obvious bad matches with configurable keywords, checks companies against a sponsor list, stores jobs in SQLite or Supabase, and gives you a Streamlit dashboard for review.

It does not auto-apply, edit resumes, generate cover letters, use RAG, or use a vector database.

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
STORAGE_BACKEND=sqlite
CONFIG_BACKEND=local
```

Using a virtual environment is recommended, but the app can still read `.env` without one.

## Storage And Config Backends

Default mode is local:

```text
STORAGE_BACKEND=sqlite
CONFIG_BACKEND=local
```

Supabase mode uses the existing Supabase schema and service role key:

```text
STORAGE_BACKEND=supabase
CONFIG_BACKEND=supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
```

`STORAGE_BACKEND` controls jobs storage. `CONFIG_BACKEND` controls whether settings come from local `config.yaml` or the Supabase `settings` table.

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

- `Jobs`: filter jobs, open links, update Action, and save notes.
- `Settings`: edit local YAML in local mode, or edit Supabase settings when `CONFIG_BACKEND=supabase`.
- `Run Pipeline`: trigger the fetch/filter/store pipeline manually.
- `Exports / Reports`: generate CSV exports.

Default job view shows accepted and pending jobs. You can filter by fetched date, Status, Action, sponsor status, company, location, keyword, and workplace type.

## Streamlit Login Setup

The dashboard uses a simple username/password login backed by bcrypt password hashes in Streamlit secrets. Users type their normal password, not the hash.

Generate a password hash locally:

```powershell
python scripts/generate_password_hash.py
```

Copy the generated hash. In Streamlit Cloud, open App settings -> Secrets and add users like this:

```toml
[auth.users.user1]
display_name = "User One"
password_hash = "$2b$12$PASTE_HASH_HERE"

[auth.users.user2]
display_name = "User Two"
password_hash = "$2b$12$PASTE_HASH_HERE"
```

The hash is generated once per password. To change a password, generate a new hash and replace the old hash in Streamlit secrets.

For local testing, create `.streamlit/secrets.toml` with the same format. Do not commit it; `.streamlit/secrets.toml` is already ignored.

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

## Sponsor Description Phrases

Some jobs explicitly say sponsorship is available. Edit `config.yaml` under `sponsorship_description_match` to add positive or negative description patterns. You can also edit these in the dashboard Settings tab.

Simple phrases work, and regex patterns are supported for flexible matching:

```yaml
sponsorship_description_match:
  positive_patterns:
    - "visa sponsorship available"
    - "skilled worker support"
  negative_patterns:
    - "no visa sponsorship"
    - "sponsorship not available"
```

Positive matches mark the sponsor as found by description before checking the sponsor list. Negative patterns prevent false positives.

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

The current version uses Streamlit with SQLite locally, and can also route storage/config to Supabase. The code is split so further migration is easier:

- Pipeline logic lives in `src/main.py` as `run_pipeline(...)`.
- Database operations are isolated behind `src/storage_router.py`, with SQLite in `src/storage.py` and Supabase in `src/supabase_storage.py`.
- Config handling is isolated in `src/config_loader.py`.
- UI code is isolated in `src/dashboard.py`.

A future hosted version could rebuild the dashboard in Next.js/Vercel or Streamlit Community Cloud, expose manual pipeline runs through an authenticated API endpoint, and add scheduled daily runs using platform cron.
