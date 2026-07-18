from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping

from pydantic import ValidationError

from arkirev.budget import estimate_impact, load_budget
from arkirev.models import ChangeItem, RevisionAnalysis
from arkirev.schedule import build_tasks, compute_cpm, load_templates

DEFAULT_BUDGET_PATH = Path("data/project_budget.json")
DEFAULT_TEMPLATES_PATH = Path("data/task_templates.json")


def run_revision_workflow(
    changes: RevisionAnalysis | list[ChangeItem | Mapping[str, Any]] | Mapping[str, Any],
    *,
    budget_path: str | Path = DEFAULT_BUDGET_PATH,
    templates_path: str | Path = DEFAULT_TEMPLATES_PATH,
    field_brief: str = "",
    risks: list[str] | None = None,
) -> dict[str, Any]:
    """Run the complete deterministic backend workflow for the UI.

    The UI should send structured change data from a form or canvas. This
    function validates that input, loads local configuration, expands the
    construction tasks, computes CPM, and estimates the budget impact.
    """
    analysis = _coerce_revision_analysis(changes, field_brief=field_brief, risks=risks)
    budget = load_budget(budget_path)
    templates = load_templates(templates_path)
    tasks = build_tasks(analysis, templates)
    schedule = compute_cpm(tasks)
    impact = estimate_impact(analysis, budget)
    schedule_payload = {
        "project_duration_days": schedule.project_duration_days,
        "critical_path": schedule.critical_path,
        "tasks": [asdict(task) for task in schedule.tasks],
    }

    return {
        "analysis": analysis.model_dump(),
        "budget": {
            "project_name": budget.project_name,
            "currency": budget.currency,
            "allotted_budget": budget.allotted_budget,
            "actual_spent": budget.actual_spent,
            "contingency_pct": budget.contingency_pct,
            "manual_review_minutes_baseline": budget.manual_review_minutes_baseline,
        },
        "impact": impact,
        "schedule": schedule_payload,
        "insights": _build_insights(analysis, impact, schedule_payload),
    }


def _coerce_revision_analysis(
    changes: RevisionAnalysis | list[ChangeItem | Mapping[str, Any]] | Mapping[str, Any],
    *,
    field_brief: str,
    risks: list[str] | None,
) -> RevisionAnalysis:
    if isinstance(changes, RevisionAnalysis):
        return changes

    if isinstance(changes, Mapping):
        try:
            return RevisionAnalysis.model_validate(changes)
        except ValidationError as exc:
            raise ValueError(f"Invalid revision analysis: {exc}") from exc

    try:
        parsed_changes = [
            change if isinstance(change, ChangeItem) else ChangeItem.model_validate(change)
            for change in changes
        ]
    except TypeError as exc:
        raise ValueError("changes must be a RevisionAnalysis, mapping, or list of changes") from exc
    except ValidationError as exc:
        raise ValueError(f"Invalid change data: {exc}") from exc

    return RevisionAnalysis(
        changes=parsed_changes,
        field_brief=field_brief,
        risks=risks or [],
    )


def _build_insights(
    analysis: RevisionAnalysis,
    impact: Mapping[str, Any],
    schedule: Mapping[str, Any],
) -> dict[str, Any]:
    changes = analysis.changes
    critical_task_ids = set(schedule["critical_path"])
    critical_tasks = [
        task for task in schedule["tasks"]
        if task["id"] in critical_task_ids
    ]
    critical_trades = sorted({task["trade"] for task in critical_tasks})
    highest_trade = _highest_trade(impact.get("by_trade", {}))
    review_flags = [change.summary for change in changes if change.verify_before_build]

    messages: list[str] = []
    if not changes:
        messages.append("No structured changes were detected, so there is no added budget or schedule impact.")
    else:
        messages.append(
            f"{len(changes)} structured change(s) add {impact['budget_at_risk']} at risk "
            f"and {schedule['project_duration_days']} day(s) to the critical-path model."
        )
    if highest_trade:
        trade, amount = highest_trade
        messages.append(f"{trade} carries the largest budget exposure at {amount}.")
    if critical_trades:
        messages.append(f"Critical-path work runs through: {', '.join(critical_trades)}.")
    if impact.get("over_budget"):
        messages.append("Projected actual is over the allotted budget after contingency.")
    elif changes:
        messages.append("Projected actual remains within the allotted budget after contingency.")
    if review_flags:
        messages.append(f"{len(review_flags)} change(s) should be verified before build.")

    return {
        "change_count": len(changes),
        "review_required_count": len(review_flags),
        "highest_cost_trade": highest_trade[0] if highest_trade else None,
        "highest_cost_trade_amount": highest_trade[1] if highest_trade else 0,
        "critical_trade_count": len(critical_trades),
        "critical_trades": critical_trades,
        "summary": " ".join(messages),
        "review_flags": review_flags,
    }


def _highest_trade(by_trade: Mapping[str, int]) -> tuple[str, int] | None:
    if not by_trade:
        return None
    trade, amount = max(by_trade.items(), key=lambda item: (item[1], item[0]))
    return trade, int(amount)
