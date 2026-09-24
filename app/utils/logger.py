"""
Structured logging with Rich for beautiful console output
and standard file logging for debugging.
"""
import logging
import sys
from pathlib import Path
from datetime import datetime

from rich.console import Console
from rich.logging import RichHandler
from rich.theme import Theme

# ── Rich console with custom theme ─────────────────────
custom_theme = Theme(
    {
        "info": "cyan",
        "warning": "yellow",
        "error": "bold red",
        "success": "bold green",
        "source": "magenta",
        "job": "bold blue",
    }
)

console = Console(theme=custom_theme)


def setup_logger(
    name: str = "job_agent",
    level: str = "INFO",
    log_dir: str | None = None,
) -> logging.Logger:
    """
    Create a logger with Rich console output + optional file handler.

    Args:
        name: Logger name.
        level: Logging level string (DEBUG, INFO, WARNING, ERROR).
        log_dir: Directory for log files. If None, only console output.

    Returns:
        Configured logger instance.
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Avoid duplicate handlers on repeated calls
    if logger.handlers:
        return logger

    # ── Rich console handler ────────────────────────────
    rich_handler = RichHandler(
        console=console,
        show_time=True,
        show_path=False,
        markup=True,
        rich_tracebacks=True,
    )
    rich_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
    rich_fmt = logging.Formatter("%(message)s", datefmt="[%X]")
    rich_handler.setFormatter(rich_fmt)
    logger.addHandler(rich_handler)

    # ── File handler (optional) ─────────────────────────
    if log_dir:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_handler = logging.FileHandler(
            log_path / f"job_agent_{timestamp}.log",
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_fmt = logging.Formatter(
            "%(asctime)s | %(name)s | %(levelname)-8s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(file_fmt)
        logger.addHandler(file_handler)

    return logger


def get_logger(name: str = "job_agent") -> logging.Logger:
    """Get an existing logger or create one with defaults."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        return setup_logger(name)
    return logger
