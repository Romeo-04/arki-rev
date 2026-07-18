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
    baseline_duration_days: float | None = None,
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
        "duration_change": _build_duration_change(schedule.project_duration_days, baseline_duration_days),
        "critical_path": schedule.critical_path,
        "tasks": [asdict(task) for task in schedule.tasks],
    }
    schedule_payload["change_windows"] = _build_change_windows(analysis, schedule_payload)

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
    duration_change = schedule.get("duration_change", {})
    if duration_change.get("baseline_duration_days") is not None:
        days_added = duration_change["days_added"]
        days_reduced = duration_change["days_reduced"]
        if days_added:
            messages.append(f"The revision adds {days_added} day(s) versus the baseline.")
        elif days_reduced:
            messages.append(f"The revision reduces the plan by {days_reduced} day(s) versus the baseline.")
        else:
            messages.append("The revision has no duration change versus the baseline.")
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


def _build_duration_change(project_duration_days: float, baseline_duration_days: float | None) -> dict[str, float | None]:
    if baseline_duration_days is None:
        return {
            "baseline_duration_days": None,
            "duration_delta_days": None,
            "days_added": 0.0,
            "days_reduced": 0.0,
        }
    if baseline_duration_days < 0:
        raise ValueError("baseline_duration_days must be non-negative")

    delta = round(project_duration_days - baseline_duration_days, 6)
    return {
        "baseline_duration_days": baseline_duration_days,
        "duration_delta_days": delta,
        "days_added": max(delta, 0.0),
        "days_reduced": abs(min(delta, 0.0)),
    }


def _build_change_windows(
    analysis: RevisionAnalysis,
    schedule: Mapping[str, Any],
) -> list[dict[str, Any]]:
    tasks_by_change: dict[int, list[Mapping[str, Any]]] = {
        index: [] for index, _ in enumerate(analysis.changes)
    }
    for task in schedule["tasks"]:
        tasks_by_change.setdefault(task["change_index"], []).append(task)

    windows: list[dict[str, Any]] = []
    for change_index, change in enumerate(analysis.changes):
        change_tasks = tasks_by_change.get(change_index, [])
        if change_tasks:
            start_day = min(task["es"] for task in change_tasks)
            finish_day = max(task["ef"] for task in change_tasks)
            work_days = round(sum(task["duration_days"] for task in change_tasks), 6)
            critical_task_ids = [task["id"] for task in change_tasks if task["critical"]]
            task_names = [task["name"] for task in change_tasks]
        else:
            start_day = 0.0
            finish_day = 0.0
            work_days = 0.0
            critical_task_ids = []
            task_names = []

        is_critical = bool(critical_task_ids)
        controls_project_finish = is_critical and finish_day == schedule["project_duration_days"]
        days_added_to_revision = finish_day if controls_project_finish else 0.0

        windows.append(
            {
                "change_index": change_index,
                "summary": change.summary,
                "category": change.category,
                "trade": change.trade,
                "start_day": start_day,
                "finish_day": finish_day,
                "implementation_days": round(finish_day - start_day, 6),
                "work_days": work_days,
                "build_window": f"Day {start_day:g} to Day {finish_day:g}",
                "critical": is_critical,
                "controls_project_finish": controls_project_finish,
                "days_added_to_revision": days_added_to_revision,
                "days_reduced_from_revision": 0.0,
                "task_ids": [task["id"] for task in change_tasks],
                "task_names": task_names,
                "critical_task_ids": critical_task_ids,
            }
        )
    return windows
