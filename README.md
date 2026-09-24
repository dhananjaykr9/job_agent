# 🔍 AI Job Discovery Agent

An AI-powered multi-source job discovery system that automatically finds relevant job opportunities and updates your Excel tracker.

## Features

- **Multi-Source Discovery**: Searches Google, LinkedIn Posts, Company Career Pages
- **AI Extraction**: Uses Google Gemini to extract structured job data from unstructured content
- **Smart Matching**: Rule-based + AI-assisted filtering (location, experience, role matching)
- **Deduplication**: Multi-level duplicate detection (URL, fingerprint, SQLite history)
- **Excel Integration**: Appends to your existing Excel tracker without touching your personal columns
- **Human Review Queue**: Flags ambiguous jobs for manual review instead of hallucinating

## Architecture

```
Source Discovery → LLM Extraction → Validation → Matching → Dedup → Excel
     ↓                                                          ↓
DuckDuckGo (Free)                                            SQLite
LinkedIn Posts                                              (history)
Career Pages
```

## Quick Start

### 1. Install Dependencies

```bash
cd job_agent
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your Gemini API key (Free at https://aistudio.google.com/apikey):
#   GEMINI_API_KEY=your_gemini_key
#   EXCEL_FILE_PATH=./jobs_tracker.xlsx
```

### 3. Customize Job Preferences

Edit `app/config/job_preferences.yaml` to set:
- Target locations
- Max experience years
- Included/excluded roles
- Search queries
- LinkedIn keywords
- Target companies

### 4. Run Discovery

```bash
# Continuous hourly discovery (runs every 1 hour automatically)
python cli.py schedule

# Or specify a custom interval (e.g. every 2 hours, or every 0.5 hours)
python cli.py schedule --interval 1

# One-time discovery run
python cli.py search

# Start the API server (includes automatic hourly scheduler in background)
python cli.py server

# View jobs pending review
python cli.py review

# View last run report
python cli.py report
```

### 5. Automatic Hands-Free Deployment

You do **NOT** need to open a terminal or run commands every day. Choose either option below:

#### Method A: Auto-Start on Laptop Boot (Silent Background Mode)
Double-click `install_startup.bat`:
- Installs the agent into your Windows Startup.
- Every time you start or log into your laptop, the agent launches silently in the background (no black CMD window).
- Automatically runs job discovery every 1 hour and appends new jobs to `jobs_tracker.xlsx`.
- To uninstall anytime: double-click `uninstall_startup.bat`.

#### Method B: 24/7 Cloud Deployment with GitHub Actions (Laptop can be OFF)
A pre-configured GitHub Actions workflow is included in `.github/workflows/job_discovery.yml`:
1. Push this repository to GitHub (make it a private repo).
2. Go to **Settings > Secrets and variables > Actions > New repository secret**.
3. Add name `GEMINI_API_KEY` with your key.
4. GitHub's cloud servers will run discovery every hour for free and commit updated rows to `jobs_tracker.xlsx`.

### 6. API Endpoints (when server is running)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/search` | Trigger a discovery run |
| GET | `/status` | Check run status |
| GET | `/report` | Last run report |
| GET | `/review` | Jobs pending review |
| GET | `/health` | Health check |
| GET | `/docs` | Swagger UI |

## Project Structure

```
job_agent/
├── app/
│   ├── agents/          # LLM-powered extraction, classification, validation
│   ├── config/          # Settings + job_preferences.yaml
│   ├── database/        # SQLite models + repository
│   ├── dedup/           # Multi-level duplicate detection
│   ├── excel/           # Read/write/map Excel columns
│   ├── graph/           # LangGraph state, nodes, workflow
│   ├── matching/        # Rule-based + AI job matching
│   ├── sources/         # Web search, LinkedIn posts, career pages
│   ├── utils/           # Logger, text normalization
│   ├── main.py          # FastAPI server
│   └── schemas.py       # All Pydantic models
├── cli.py               # CLI entry point
├── .env.example         # Environment template
└── requirements.txt     # Python dependencies
```

## Excel Column Mapping

The agent writes to these columns:
| Excel Column | Internal Field |
|---|---|
| Company | company_name |
| Role | job_title |
| Location | location |
| Experience | experience |
| Tech | skills |
| Job URL | job_url (as hyperlink) |
| Recruiter | recruiter_name |

These columns are **never touched** by the agent:
- Applied
- Employee Contacted
- Follow-up Date
- Status

## Tech Stack

- **Python 3.11+** — Core runtime
- **LangGraph** — Workflow orchestration
- **Google Gemini** — LLM extraction & classification
- **DuckDuckGo Search** — Web search (100% free, no API key needed)
- **httpx + BeautifulSoup** — Page scraping
- **SQLite + SQLAlchemy** — Job history database
- **OpenPyXL** — Excel automation
- **FastAPI** — REST API
- **Rich** — Terminal output

## License

MIT
