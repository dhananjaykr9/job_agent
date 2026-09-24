"""
Google Sheets integration module.

Provides:
1. Live Google Sheet reading via export URL (no auth required for shared sheets).
2. Live Google Sheet appending via Google Apps Script Webhook (zero GCP setup).
"""
from __future__ import annotations

import re
import httpx
from pathlib import Path
from ..schemas import JobCandidate
from .mapper import ExcelMapper
from ..utils.logger import get_logger

logger = get_logger("job_agent.excel.google_sheets")


def extract_spreadsheet_id(url: str) -> str | None:
    """Extract the spreadsheet ID from any Google Sheet URL."""
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", url)
    if match:
        return match.group(1)
    return None


def fetch_live_google_sheet(sheet_url: str, save_path: str | Path) -> bool:
    """
    Download the latest version of a shared Google Sheet as an .xlsx file.
    Ensures the agent is always working with the user's latest data/edits.
    """
    sheet_id = extract_spreadsheet_id(sheet_url)
    if not sheet_id:
        logger.warning(f"Could not extract spreadsheet ID from URL: {sheet_url}")
        return False

    export_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"

    try:
        logger.info("Fetching latest data from live Google Sheet...")
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            resp = client.get(export_url)
            resp.raise_for_status()

            # Ensure parent directories exist
            target = Path(save_path)
            target.parent.mkdir(parents=True, exist_ok=True)

            with open(target, "wb") as f:
                f.write(resp.content)

            logger.info(f"Successfully synced live Google Sheet to {target.name} ({len(resp.content)} bytes)")
            return True
    except Exception as e:
        logger.warning(f"Failed to fetch live Google Sheet (using local file fallback): {e}")
        return False


def append_to_google_sheet_webhook(
    webhook_url: str,
    jobs: list[JobCandidate],
    mapper: ExcelMapper,
    headers: list[str],
) -> int:
    """
    Send newly discovered jobs directly to the Google Sheet via Apps Script Webhook.

    Each job is mapped to match the exact column order of the Google Sheet.
    """
    if not webhook_url or not jobs:
        return 0

    # Format each job as a list matching the sheet's column order
    rows_to_append = []
    for job in jobs:
        row_dict = mapper.job_to_row(job)
        row_values = []
        for header in headers:
            val = row_dict.get(header, "")
            # None or missing becomes empty string
            row_values.append("" if val is None else str(val))
        rows_to_append.append(row_values)

    try:
        logger.info(f"Syncing {len(rows_to_append)} new jobs to live Google Sheet...")
        with httpx.Client(timeout=45.0, follow_redirects=True) as client:
            resp = client.post(
                webhook_url,
                json={"rows": rows_to_append},
            )
            resp.raise_for_status()
            res_json = resp.json()
            if res_json.get("status") == "success":
                added = res_json.get("added", len(rows_to_append))
                logger.info(f"[bold green]Successfully added {added} rows directly to live Google Sheet![/]")
                return added
            else:
                logger.warning(f"Google Sheet webhook returned message: {res_json}")
                return len(rows_to_append)
    except Exception as e:
        logger.error(f"Failed to append to live Google Sheet via webhook: {e}")
        return 0
