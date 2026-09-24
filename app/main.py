"""
FastAPI application — HTTP API for the job discovery agent.

Endpoints:
    POST /search          — Trigger a discovery run
    GET  /status          — Check if a run is in progress
    GET  /report          — Get the last run report
    GET  /review          — Get jobs pending human review
    POST /review/{id}     — Approve or reject a reviewed job
    GET  /health          — Health check
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel

from .graph.workflow import run_discovery
from .database.repository import JobRepository
from .config.settings import get_settings
from .utils.logger import setup_logger, get_logger

# ── State ───────────────────────────────────────────────
_current_run: dict | None = None
_last_report: dict | None = None
_is_running = False
_scheduler = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize on startup, start background scheduler, cleanup on shutdown."""
    settings = get_settings()
    logger = setup_logger("job_agent", level=settings.log_level, log_dir="./logs")
    logger.info("Job Discovery Agent API starting...")

    # Start background scheduler for hourly runs
    global _scheduler
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        _scheduler = BackgroundScheduler()
        _scheduler.add_job(
            _run_discovery_task,
            "interval",
            hours=settings.schedule_interval_hours,
            id="hourly_discovery",
            replace_existing=True,
        )
        _scheduler.start()
        logger.info(
            f"Hourly discovery scheduler active — running every {settings.schedule_interval_hours} hour(s)"
        )
    except Exception as e:
        logger.warning(f"Background scheduler initialization note: {e}")

    yield

    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
    logger.info("Shutting down.")


app = FastAPI(
    title="AI Job Discovery Agent",
    description="Automatically discover and track job opportunities",
    version="1.0.0",
    lifespan=lifespan,
)

logger = get_logger("job_agent.api")


# ── Request/Response Models ─────────────────────────────
class SearchRequest(BaseModel):
    """Optional overrides for a discovery run."""
    queries: Optional[list[str]] = None


class ReviewAction(BaseModel):
    action: str  # "approve" or "reject"


# ── Background task runner ──────────────────────────────
def _run_discovery_task():
    """Run discovery in background thread."""
    global _current_run, _last_report, _is_running

    _is_running = True
    _current_run = {"started_at": datetime.now().isoformat(), "status": "running"}

    try:
        report = run_discovery()
        _last_report = report
        _current_run["status"] = "completed"
        _current_run["completed_at"] = datetime.now().isoformat()
        _current_run["report"] = report
    except Exception as e:
        logger.error(f"Discovery run failed: {e}")
        _current_run["status"] = "failed"
        _current_run["error"] = str(e)
    finally:
        _is_running = False


# ── Endpoints ───────────────────────────────────────────
@app.post("/search", summary="Trigger a job discovery run")
async def trigger_search(
    request: SearchRequest = SearchRequest(),
    background_tasks: BackgroundTasks = None,
):
    """Start a new job discovery run in the background."""
    global _is_running

    if _is_running:
        raise HTTPException(
            status_code=409, detail="A discovery run is already in progress."
        )

    background_tasks.add_task(_run_discovery_task)
    return {
        "status": "started",
        "message": "Discovery run started in background. Check /status for progress.",
    }


@app.get("/status", summary="Check run status")
async def get_status():
    """Get the status of the current or last run."""
    if _is_running:
        return {"status": "running", "run": _current_run}
    if _current_run:
        return {"status": _current_run.get("status", "unknown"), "run": _current_run}
    return {"status": "idle", "message": "No runs have been executed yet."}


@app.get("/report", summary="Get last run report")
async def get_report():
    """Get the detailed report from the last completed run."""
    if _last_report:
        return _last_report
    return {"message": "No completed runs yet."}


@app.get("/review", summary="Get jobs pending review")
async def get_review_jobs():
    """Get all jobs that need human review."""
    try:
        settings = get_settings()
        repo = JobRepository(settings.database_url)
        jobs = repo.get_review_jobs()
        return {
            "count": len(jobs),
            "jobs": [
                {
                    "id": j.id,
                    "company": j.company_name,
                    "title": j.job_title,
                    "location": j.location,
                    "url": j.job_url,
                    "confidence": j.confidence_score,
                    "review_reason": j.review_reason,
                    "source": j.source,
                }
                for j in jobs
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/schedule", summary="Check automatic scheduler status")
async def get_schedule():
    """Get the status of the automatic hourly scheduler."""
    settings = get_settings()
    is_active = bool(_scheduler and _scheduler.running)
    next_run = None
    if is_active:
        job = _scheduler.get_job("hourly_discovery")
        if job and job.next_run_time:
            next_run = job.next_run_time.isoformat()
    return {
        "scheduler_active": is_active,
        "interval_hours": settings.schedule_interval_hours,
        "next_run_time": next_run,
        "is_currently_running": _is_running,
    }


@app.get("/health", summary="Health check")
async def health():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}
