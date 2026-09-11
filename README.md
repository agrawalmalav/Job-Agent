# Job Search Agent

A Python-based job discovery and tracking platform built for UK tech job searches, with sponsorship-aware filtering, configurable matching rules, SQLite/Supabase storage, scheduled data ingestion and a Streamlit review dashboard.

The current version focuses on building a reliable **job-search data pipeline and review workflow**. Agentic relevance scoring, evidence-based resume tailoring and human-in-the-loop application support are planned next steps rather than current capabilities.

## What it does

```mermaid
flowchart LR
    A[LinkedIn search URLs] --> B[Apify ingestion]
    B --> C[Field cleaning]
    C --> D[Deterministic filters]
    D --> E[Sponsorship checks]
    E --> F[SQLite / Supabase]
    F --> G[Streamlit dashboard]
    G --> H[Review, status + notes]
```

## Current capabilities

### Job ingestion

- Fetches LinkedIn job results through Apify
- Supports multiple configured search URLs
- Normalises and cleans common job fields
- Skips duplicates across repeat runs

### Deterministic filtering

Configurable rules filter out jobs based on criteria such as:

- employment type
- unwanted role categories
- seniority terms
- visa / clearance language
- contract terminology

The filtering layer is intentionally deterministic so obvious exclusions do not depend on an LLM.

### Sponsorship checks

The pipeline evaluates sponsorship using two signals:

1. explicit positive/negative sponsorship phrases in the job description
2. company matching against a UK sponsor-list dataset

Company aliases can be configured for cases where a trading name differs from the sponsor-list entity.

> Presence on the sponsor list does not guarantee that a specific vacancy offers sponsorship.

### Storage

The application supports two storage/configuration modes:

- **SQLite + local YAML** for fully local use
- **Supabase** for hosted/shared persistence

Storage access is routed behind dedicated modules rather than embedded directly in the UI or pipeline.

### Review dashboard

The Streamlit dashboard supports:

- job filtering and search
- opening original vacancy links
- sponsorship status review
- application actions/statuses
- notes
- editable settings
- manual pipeline execution
- CSV exports and reports

### Authentication

The Streamlit UI supports username/password login using bcrypt password hashes stored in Streamlit secrets.

### Automation

A GitHub Actions workflow can run the pipeline on a daily schedule and also supports manual execution.

## Tech stack

- Python 3.11+
- Streamlit
- Apify
- SQLite
- Supabase
- pandas
- bcrypt
- pytest
- GitHub Actions

## Repository structure

```text
src/
  apify_fetcher.py        Job ingestion
  basic_filter.py         Deterministic exclusion rules
  sponsor_checker.py      Sponsorship matching
  field_cleaner.py        Input normalisation
  storage.py              SQLite persistence
  supabase_storage.py     Supabase persistence
  storage_router.py       Backend abstraction
  dashboard.py            Streamlit UI
  config_loader.py        Local/Supabase configuration
  main.py                 Pipeline orchestration

tests/                    Unit tests
scripts/                  Utility scripts
.github/workflows/        Scheduled pipeline automation
config.yaml               Search/filter configuration
data/                      Sponsor data and aliases
```

## Quick start

### 1. Install

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

Copy `.env.example` and set at least:

```ini
APIFY_TOKEN=your-token
STORAGE_BACKEND=sqlite
CONFIG_BACKEND=local
```

For Supabase mode:

```ini
STORAGE_BACKEND=supabase
CONFIG_BACKEND=supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
```

### 3. Configure searches

Edit `config.yaml` and add one or more LinkedIn search URLs:

```yaml
linkedin_search_urls:
  - "https://www.linkedin.com/jobs/search/..."
```

### 4. Run the pipeline

```bash
python -m src.main
```

Use the most recent locally fetched input without calling Apify again:

```bash
python -m src.main --no-fetch
```

### 5. Launch the dashboard

```bash
streamlit run src/dashboard.py
```

## Job statuses

The project deliberately separates machine-generated pipeline state from user application state.

### Pipeline status

- `accepted`
- `manual_review`
- `rejected`
- `duplicate` (reserved for future run tracking)

### User status

- `pending`
- `applied`
- `rejected`
- `referral_requested`
- `interview_scheduled`
- `closed`

Repeat ingestion does not overwrite user notes or application status for an existing job.

## Testing

Run the test suite with:

```bash
pytest
```

The current tests cover ingestion, field cleaning, deterministic filtering, sponsorship matching and storage behaviour.

## Why this architecture?

### Deterministic first, AI where it adds value

Eligibility rules, duplicate handling and sponsor-list matching are deterministic problems. Keeping those outside an LLM makes the pipeline cheaper, easier to test and easier to reason about.

The planned AI layer is reserved for tasks where semantic reasoning is actually useful, such as role fit, company research and evidence-based tailoring.

### Storage abstraction

The repository can move between local SQLite and Supabase without coupling core pipeline logic to one database implementation.

## Roadmap

The next phase is to evolve the platform from a job-search pipeline into a supervised agentic workflow:

- LLM-based role relevance scoring
- company and vacancy research
- candidate-profile / evidence retrieval
- evidence-based resume bullet selection and tailoring
- optional cover-letter drafting
- LangGraph orchestration for reasoning-heavy stages
- human-in-the-loop approval before generated application material is used
- structured Pydantic outputs
- prompt/evaluation regression cases
- FastAPI service layer
- tracing and observability
- separation of CI checks from the scheduled production workflow
- automatic sponsor-list refresh rather than committing the full dataset

## Scope

The current repository **does not auto-apply to jobs** and does not currently perform resume or cover-letter tailoring. Those capabilities are intentionally listed under the roadmap above so the documented state matches the implementation.