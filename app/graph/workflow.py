"""
LangGraph Workflow — the core orchestration graph.

This wires all nodes into a directed graph that implements
the complete job discovery pipeline:

  load_config → [sources in parallel] → extract → validate
  → match → deduplicate → write_excel → save_reviews → report
"""
from __future__ import annotations

from langgraph.graph import StateGraph, START, END

from .state import JobSearchState
from .nodes import (
    load_config,
    search_web,
    search_linkedin_posts,
    search_company_careers,
    search_direct_boards,
    extract_jobs,
    validate_jobs,
    match_jobs,
    deduplicate_jobs,
    write_to_excel,
    save_review_jobs,
    generate_report,
)
from ..utils.logger import get_logger

logger = get_logger("job_agent.workflow")


def build_workflow() -> StateGraph:
    """
    Build and compile the LangGraph job discovery workflow.

    Graph structure:

        START
          │
          ▼
      load_config
          │
          ├──────────────────────────┐──────────────────────┐
          ▼                         ▼                      ▼
     search_web          search_linkedin       search_careers
          │                         │                      │
          └──────────────────────────┘──────────────────────┘
                                    │
                                    ▼
                              extract_jobs
                                    │
                                    ▼
                             validate_jobs
                                    │
                                    ▼
                              match_jobs
                                    │
                                    ▼
                           deduplicate_jobs
                                    │
                                    ▼
                           write_to_excel
                                    │
                                    ▼
                          save_review_jobs
                                    │
                                    ▼
                          generate_report
                                    │
                                    ▼
                                   END
    """
    graph = StateGraph(JobSearchState)

    # ── Add nodes ───────────────────────────────────────
    graph.add_node("load_config", load_config)
    graph.add_node("search_web", search_web)
    graph.add_node("search_linkedin", search_linkedin_posts)
    graph.add_node("search_careers", search_company_careers)
    graph.add_node("search_direct", search_direct_boards)
    graph.add_node("extract_jobs", extract_jobs)
    graph.add_node("validate_jobs", validate_jobs)
    graph.add_node("match_jobs", match_jobs)
    graph.add_node("deduplicate_jobs", deduplicate_jobs)
    graph.add_node("write_to_excel", write_to_excel)
    graph.add_node("save_review_jobs", save_review_jobs)
    graph.add_node("generate_report", generate_report)

    # ── Wire edges ──────────────────────────────────────

    # START → load_config
    graph.add_edge(START, "load_config")

    # Sequential search discovery (accumulates into raw_results safely)
    graph.add_edge("load_config", "search_web")
    graph.add_edge("search_web", "search_linkedin")
    graph.add_edge("search_linkedin", "search_careers")
    graph.add_edge("search_careers", "search_direct")

    # All sources done -> Extraction
    graph.add_edge("search_direct", "extract_jobs")

    # Sequential pipeline
    graph.add_edge("extract_jobs", "validate_jobs")
    graph.add_edge("validate_jobs", "match_jobs")
    graph.add_edge("match_jobs", "deduplicate_jobs")
    graph.add_edge("deduplicate_jobs", "write_to_excel")
    graph.add_edge("write_to_excel", "save_review_jobs")
    graph.add_edge("save_review_jobs", "generate_report")

    # generate_report → END
    graph.add_edge("generate_report", END)

    return graph


def create_agent():
    """Build and compile the workflow, returning a runnable agent."""
    graph = build_workflow()
    agent = graph.compile()
    logger.info("Job discovery agent compiled and ready.")
    return agent


def run_discovery() -> dict:
    """
    Execute a full job discovery run.

    Returns the final state dict including the report.
    """
    from datetime import datetime

    agent = create_agent()

    initial_state = {
        "raw_results": [],
        "errors": [],
    }

    logger.info("Starting discovery run...")
    result = agent.invoke(initial_state)

    return result.get("report", {})
