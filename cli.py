"""
CLI entry point for the Job Discovery Agent.

Usage:
    python cli.py search          — Run a full discovery cycle
    python cli.py review          — Show jobs pending review
    python cli.py report          — Show last run report
    python cli.py server          — Start the FastAPI server
"""
from __future__ import annotations

import sys
import json
import argparse
from datetime import datetime

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    console = Console()
except ImportError:
    class DummyConsole:
        def print(self, *args, **kwargs):
            import re
            cleaned = [re.sub(r"\[/?[^\]]+\]", "", str(a)) for a in args]
            print(*cleaned)
    class DummyPanel:
        @staticmethod
        def fit(text, border_style=None):
            return f"\n{'='*50}\n{text}\n{'='*50}"
    console = DummyConsole()
    Panel = DummyPanel
    Table = None


def cmd_search(args):
    """Run a full job discovery cycle."""
    from app.graph.workflow import run_discovery
    from app.utils.logger import setup_logger
    from app.config.settings import get_settings

    settings = get_settings()
    setup_logger("job_agent", level=settings.log_level, log_dir="./logs")

    console.print(
        Panel.fit(
            "[bold cyan]🔍 AI Job Discovery Agent[/]\n"
            f"[dim]Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/]",
            border_style="cyan",
        )
    )

    report = run_discovery()

    # Summary table
    table = Table(title="Discovery Run Summary", show_header=False, border_style="cyan")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")

    table.add_row("Raw results", str(report.get("total_raw", 0)))
    table.add_row("Extracted", str(report.get("total_extracted", 0)))
    table.add_row("Validated", str(report.get("total_validated", 0)))
    table.add_row("Matched", str(report.get("total_matched", 0)))
    table.add_row("Duplicates", str(report.get("total_duplicates", 0)))
    table.add_row("Rejected", str(report.get("total_rejected", 0)))
    table.add_row("Review needed", str(report.get("total_review", 0)))
    table.add_row(
        "[bold green]Added to Excel[/]",
        f"[bold green]{report.get('total_added', 0)}[/]",
    )

    console.print(table)

    if report.get("errors"):
        console.print(f"\n[yellow]⚠ {len(report['errors'])} errors occurred:[/]")
        for err in report["errors"]:
            console.print(f"  [dim]→ {err}[/]")


def cmd_schedule(args):
    """Run job discovery on a recurring schedule (default: every 1 hour)."""
    import time
    from app.graph.workflow import run_discovery
    from app.utils.logger import setup_logger
    from app.config.settings import get_settings

    settings = get_settings()
    setup_logger("job_agent", level=settings.log_level, log_dir="./logs")

    interval_hours = args.interval if args.interval is not None else settings.schedule_interval_hours
    interval_seconds = int(interval_hours * 3600)

    console.print(
        Panel.fit(
            f"[bold cyan]⏰ AI Job Discovery Agent — Hourly Scheduler[/]\n"
            f"Interval: Every [bold yellow]{interval_hours} hour(s)[/]\n"
            f"[dim]Runs automatically in background. Press Ctrl+C to stop.[/]",
            border_style="cyan",
        )
    )

    run_count = 0
    try:
        while True:
            run_count += 1
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            console.print(f"\n[bold cyan]{'━' * 60}[/]")
            console.print(f"[bold green]▶ Starting Scheduled Run #{run_count}[/] at {now_str}")
            console.print(f"[bold cyan]{'━' * 60}[/]")
            try:
                report = run_discovery()
                added = report.get("total_added", 0)
                console.print(
                    f"\n[bold green]✓ Run #{run_count} completed![/] Added [bold]{added}[/] new jobs to Excel."
                )
            except Exception as e:
                console.print(f"\n[bold red]✗ Run #{run_count} encountered an error:[/] {e}")

            next_run = datetime.fromtimestamp(time.time() + interval_seconds)
            console.print(
                f"\n[dim]⏳ Next run in {interval_hours}h at {next_run.strftime('%Y-%m-%d %H:%M:%S')}. Sleeping...[/]"
            )
            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        console.print("\n[yellow]Scheduler stopped by user.[/]")


def cmd_review(args):
    """Show jobs pending human review."""
    from app.database.repository import JobRepository
    from app.config.settings import get_settings

    settings = get_settings()
    repo = JobRepository(settings.database_url)
    jobs = repo.get_review_jobs()

    if not jobs:
        console.print("[green]✓ No jobs pending review.[/]")
        return

    table = Table(title=f"Jobs Pending Review ({len(jobs)})", border_style="yellow")
    table.add_column("ID", style="dim")
    table.add_column("Company", style="bold")
    table.add_column("Title", style="cyan")
    table.add_column("Location")
    table.add_column("Confidence", justify="right")
    table.add_column("Reason", style="dim")

    for j in jobs:
        table.add_row(
            str(j.id),
            j.company_name,
            j.job_title,
            j.location,
            f"{j.confidence_score:.0%}",
            (j.review_reason or "")[:50],
        )

    console.print(table)
    console.print(
        "\n[dim]Use the /review endpoint or add jobs manually to your Excel.[/]"
    )


def cmd_report(args):
    """Show the last run report from the database."""
    from app.database.models import SearchRun, init_database
    from app.config.settings import get_settings

    settings = get_settings()
    _, Session = init_database(settings.database_url)
    session = Session()

    last_run = session.query(SearchRun).order_by(SearchRun.id.desc()).first()
    session.close()

    if not last_run:
        console.print("[yellow]No runs found in database.[/]")
        return

    report_data = json.loads(last_run.report_json) if last_run.report_json else {}

    console.print(
        Panel.fit(
            f"[bold]Last Run Report[/]\n"
            f"Started:  {last_run.started_at}\n"
            f"Completed: {last_run.completed_at}\n"
            f"Added:    [bold green]{last_run.total_added}[/] jobs",
            border_style="cyan",
        )
    )

    if report_data:
        console.print_json(json.dumps(report_data, indent=2))


def cmd_server(args):
    """Start the FastAPI server."""
    import uvicorn
    from app.utils.logger import setup_logger
    from app.config.settings import get_settings

    settings = get_settings()
    setup_logger("job_agent", level=settings.log_level, log_dir="./logs")

    console.print(
        Panel.fit(
            "[bold cyan]🚀 Starting Job Discovery API Server[/]\n"
            f"[dim]http://localhost:{args.port}[/]\n"
            f"[dim]Docs: http://localhost:{args.port}/docs[/]",
            border_style="cyan",
        )
    )

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


def main():
    parser = argparse.ArgumentParser(
        description="AI Job Discovery Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python cli.py search          Run a full discovery cycle\n"
            "  python cli.py review          Show jobs pending review\n"
            "  python cli.py report          Show last run report\n"
            "  python cli.py server          Start the API server\n"
            "  python cli.py server --port 8080  Start on a custom port\n"
        ),
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # search
    sub_search = subparsers.add_parser("search", help="Run a full discovery cycle")

    # schedule (hourly by default)
    sub_sched = subparsers.add_parser(
        "schedule", help="Run discovery on a recurring schedule (default: every 1 hour)"
    )
    sub_sched.add_argument(
        "--interval",
        type=float,
        default=None,
        help="Interval between runs in hours (e.g., 1 for hourly, 0.5 for 30 mins). Default: from .env SCHEDULE_INTERVAL_HOURS",
    )

    # review
    sub_review = subparsers.add_parser("review", help="Show jobs pending review")

    # report
    sub_report = subparsers.add_parser("report", help="Show last run report")

    # server
    sub_server = subparsers.add_parser("server", help="Start the API server")
    sub_server.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    sub_server.add_argument("--port", type=int, default=8000, help="Port to bind to")
    sub_server.add_argument("--reload", action="store_true", help="Enable hot reload")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    commands = {
        "search": cmd_search,
        "schedule": cmd_schedule,
        "review": cmd_review,
        "report": cmd_report,
        "server": cmd_server,
    }

    commands[args.command](args)


if __name__ == "__main__":
    main()
