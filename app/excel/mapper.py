"""
Excel Column Mapper — maps internal JobCandidate fields to
the user's actual Excel column headers.

Supports both explicit config mapping and intelligent auto-detection.
"""
from __future__ import annotations

from ..schemas import JobCandidate
from ..utils.logger import get_logger

logger = get_logger("job_agent.excel.mapper")

# Default mapping: Excel Column → Internal Field
DEFAULT_MAPPING: dict[str, str] = {
    "Company": "company_name",
    "Company Name": "company_name",
    "Role": "job_title",
    "Position": "job_title",
    "Position Available": "job_title",
    "Job Title": "job_title",
    "Location": "location",
    "Address": "location",
    "City": "location",
    "Experience": "experience",
    "Exp": "experience",
    "Tech": "skills",
    "Skills": "skills",
    "Technologies": "skills",
    "Tech Stack": "skills",
    "Job URL": "job_url",
    "Link": "job_url",
    "URL": "job_url",
    "Apply Link": "job_url",
    "Recruiter": "recruiter_name",
    "Recruiter Name": "recruiter_name",
    "Contact": "recruiter_contact",
    "Email": "recruiter_contact",
    "Source": "source",
    "Date Added": "discovered_at",
    "Posting Date": "posting_date",
}


class ExcelMapper:
    """Maps between internal fields and Excel columns."""

    def __init__(
        self,
        excel_headers: list[str],
        custom_mapping: dict[str, str] | None = None,
        user_owned_columns: list[str] | None = None,
    ):
        self.excel_headers = excel_headers
        self.user_owned = set(user_owned_columns or [])

        # Build the mapping: Excel Column Name → Internal Field Name
        self._mapping: dict[str, str] = {}
        effective_mapping = {**DEFAULT_MAPPING}
        if custom_mapping:
            effective_mapping.update(custom_mapping)

        for header in excel_headers:
            if not header:
                continue
            if header in self.user_owned:
                continue
            if header in effective_mapping:
                self._mapping[header] = effective_mapping[header]

        logger.info(
            f"Column mapping: {self._mapping} | "
            f"User-owned: {self.user_owned}"
        )

    @property
    def writable_columns(self) -> dict[str, str]:
        """Excel Column → Internal Field for agent-writable columns."""
        return dict(self._mapping)

    def job_to_row(self, job: JobCandidate) -> dict[str, str]:
        """
        Convert a JobCandidate to a dict of {Excel Column: value}.

        Only populates columns the agent is allowed to write to.
        User-owned columns are left as None (will be skipped by writer).
        """
        row: dict[str, str | None] = {}

        for excel_col in self.excel_headers:
            if not excel_col:
                continue

            if excel_col in self.user_owned:
                row[excel_col] = None  # Don't touch user-owned
                continue

            field_name = self._mapping.get(excel_col)
            if field_name is None:
                row[excel_col] = None  # Unknown column — don't touch
                continue

            value = getattr(job, field_name, "")

            # Special handling for list fields
            if isinstance(value, list):
                value = ", ".join(str(v) for v in value)

            row[excel_col] = str(value) if value else ""

        return row
