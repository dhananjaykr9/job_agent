"""
Application settings loaded from environment variables.
"""
from pydantic_settings import BaseSettings
from pydantic import Field
from pathlib import Path
import yaml


class Settings(BaseSettings):
    """Core application settings from .env file."""

    gemini_api_key: str = Field(..., alias="GEMINI_API_KEY")
    excel_file_path: str = Field(default="./jobs_tracker.xlsx", alias="EXCEL_FILE_PATH")
    database_url: str = Field(default="sqlite:///./job_agent.db", alias="DATABASE_URL")
    gemini_model: str = Field(default="gemini-2.0-flash", alias="GEMINI_MODEL")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    schedule_interval_hours: int = Field(default=1, alias="SCHEDULE_INTERVAL_HOURS")
    google_sheet_url: str = Field(
        default="https://docs.google.com/spreadsheets/d/1Naq2pmSfyt8ulXpq-7SKFmXfaerYnvkbjSy83SXRmT0/edit?usp=sharing",
        alias="GOOGLE_SHEET_URL",
    )
    google_sheet_webhook_url: str = Field(default="", alias="GOOGLE_SHEET_WEBHOOK_URL")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "populate_by_name": True,
    }


class JobPreferences:
    """Job search preferences loaded from YAML config."""

    def __init__(self, config_path: str | None = None):
        if config_path is None:
            config_path = str(Path(__file__).parent / "job_preferences.yaml")
        with open(config_path, "r", encoding="utf-8") as f:
            self._config: dict = yaml.safe_load(f)

    # ── Location ──────────────────────────────────────
    @property
    def locations(self) -> list[str]:
        return self._config.get("location", {}).get("include", [])

    # ── Experience ────────────────────────────────────
    @property
    def max_experience_years(self) -> int:
        return self._config.get("experience", {}).get("maximum_years", 1)

    # ── Roles ─────────────────────────────────────────
    @property
    def included_roles(self) -> list[str]:
        return self._config.get("roles", {}).get("include", [])

    @property
    def excluded_roles(self) -> list[str]:
        return self._config.get("roles", {}).get("exclude", [])

    # ── Job Status ────────────────────────────────────
    @property
    def active_only(self) -> bool:
        return self._config.get("job_status", {}).get("active_only", True)

    @property
    def max_age_days(self) -> int:
        return self._config.get("posting_date", {}).get("maximum_age_days", 30)

    # ── Search Queries ────────────────────────────────
    @property
    def search_queries(self) -> list[str]:
        return self._config.get("search_queries", [])

    @property
    def linkedin_keywords(self) -> list[str]:
        return self._config.get("linkedin_post_keywords", [])

    # ── Target Companies ──────────────────────────────
    @property
    def target_companies(self) -> list[dict]:
        return self._config.get("target_companies", [])

    # ── Confidence Thresholds ─────────────────────────
    @property
    def auto_add_threshold(self) -> float:
        return self._config.get("confidence_thresholds", {}).get("auto_add", 0.80)

    @property
    def review_threshold(self) -> float:
        return self._config.get("confidence_thresholds", {}).get("review", 0.50)

    @property
    def reject_threshold(self) -> float:
        return self._config.get("confidence_thresholds", {}).get("reject", 0.30)

    # ── Excel Mapping ─────────────────────────────────
    @property
    def excel_column_mapping(self) -> dict[str, str]:
        return self._config.get("excel_column_mapping", {})

    @property
    def user_owned_columns(self) -> list[str]:
        return self._config.get("user_owned_columns", [])

    # ── Dynamic Discovery ─────────────────────────────
    @property
    def company_discovery_queries(self) -> list[str]:
        return self._config.get("company_discovery_queries", [])

    @property
    def walkin_queries(self) -> list[str]:
        return self._config.get("walkin_queries", [])

    # ── Raw config access ─────────────────────────────
    @property
    def config(self) -> dict:
        return self._config


# ── Singletons ──────────────────────────────────────────
_settings: Settings | None = None
_preferences: JobPreferences | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def get_preferences(config_path: str | None = None) -> JobPreferences:
    global _preferences
    if _preferences is None:
        _preferences = JobPreferences(config_path)
    return _preferences
