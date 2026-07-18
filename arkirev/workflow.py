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

    insights = _build_insights(analysis, impact, schedule_payload)
    report = _build_mvp_report(analysis, impact, schedule_payload, insights)

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
        "insights": insights,
        "report": report,
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


def _build_mvp_report(
    analysis: RevisionAnalysis,
    impact: Mapping[str, Any],
    schedule: Mapping[str, Any],
    insights: Mapping[str, Any],
) -> dict[str, Any]:
    change_windows = schedule["change_windows"]
    critical_windows = [window for window in change_windows if window["critical"]]
    primary_window = _primary_window(change_windows)
    risk_level = _risk_level(analysis, impact, schedule)

    changed_items = [
        {
            "change_index": index,
            "summary": change.summary,
            "category": change.category,
            "trade": change.trade,
            "severity": change.severity,
            "verify_before_build": change.verify_before_build,
            "bbox": change.bbox,
            "implementation_window": change_windows[index]["build_window"] if index < len(change_windows) else None,
            "predicted_tasks": change_windows[index]["task_names"] if index < len(change_windows) else [],
        }
        for index, change in enumerate(analysis.changes)
    ]

    prediction = {
        "risk_level": risk_level,
        "budget_at_risk": impact["budget_at_risk"],
        "over_budget": impact["over_budget"],
        "project_duration_days": schedule["project_duration_days"],
        "days_added": schedule["duration_change"]["days_added"],
        "days_reduced": schedule["duration_change"]["days_reduced"],
        "likely_bottleneck_trades": insights["critical_trades"],
        "highest_cost_trade": insights["highest_cost_trade"],
        "highest_cost_trade_amount": insights["highest_cost_trade_amount"],
    }

    field_actions = _build_field_actions(analysis, impact, schedule)
    sections = _build_report_sections(analysis, impact, schedule, insights, primary_window, risk_level)

    return {
        "title": "Revision impact summary",
        "executive_summary": _build_executive_summary(analysis, impact, schedule, insights, primary_window, risk_level),
        "field_brief": analysis.field_brief,
        "what_changed": changed_items,
        "prediction": prediction,
        "implementation_plan": {
            "overall_window": f"Day 0 to Day {schedule['project_duration_days']:g}",
            "project_duration_days": schedule["project_duration_days"],
            "duration_change": schedule["duration_change"],
            "critical_changes": [
                {
                    "change_index": window["change_index"],
                    "summary": window["summary"],
                    "build_window": window["build_window"],
                    "task_names": window["task_names"],
                }
                for window in critical_windows
            ],
            "change_windows": change_windows,
        },
        "cost_prediction": {
            "budget_at_risk": impact["budget_at_risk"],
            "contingency": impact["contingency"],
            "projected_actual": impact["projected_actual"],
            "remaining_allotment": impact["remaining_allotment"],
            "over_budget": impact["over_budget"],
            "by_trade": impact["by_trade"],
        },
        "risks": analysis.risks,
        "field_actions": field_actions,
        "sections": sections,
    }


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


def _primary_window(change_windows: list[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    if not change_windows:
        return None
    return max(
        change_windows,
        key=lambda window: (
            bool(window["controls_project_finish"]),
            window["finish_day"],
            window["implementation_days"],
        ),
    )


def _risk_level(
    analysis: RevisionAnalysis,
    impact: Mapping[str, Any],
    schedule: Mapping[str, Any],
) -> str:
    severities = {change.severity for change in analysis.changes}
    if impact["over_budget"] or "high" in severities or schedule["duration_change"]["days_added"] >= 5:
        return "high"
    if impact["budget_at_risk"] > 0 or "medium" in severities or schedule["project_duration_days"] > 0:
        return "medium"
    return "low"


def _build_executive_summary(
    analysis: RevisionAnalysis,
    impact: Mapping[str, Any],
    schedule: Mapping[str, Any],
    insights: Mapping[str, Any],
    primary_window: Mapping[str, Any] | None,
    risk_level: str,
) -> str:
    if not analysis.changes:
        return "No construction-relevant floor-plan changes were detected."

    brief = analysis.field_brief.strip() or "The revised floor plan introduces construction-relevant changes."
    timing = (
        f"The controlling work is '{primary_window['summary']}' from {primary_window['build_window']}."
        if primary_window
        else "No implementation window was generated."
    )
    return (
        f"{brief} Expected impact is {impact['budget_at_risk']} at risk, "
        f"{schedule['project_duration_days']} day(s) of revision work, and {risk_level} delivery risk. "
        f"{timing} {insights['summary']}"
    )


def _build_field_actions(
    analysis: RevisionAnalysis,
    impact: Mapping[str, Any],
    schedule: Mapping[str, Any],
) -> list[str]:
    if not analysis.changes:
        return ["No field action required until a construction-relevant change is identified."]

    actions = ["Review the marked floor-plan changes with the site lead before releasing work."]
    review_required = [change.summary for change in analysis.changes if change.verify_before_build]
    if review_required:
        actions.append(f"Verify before build: {', '.join(review_required)}.")
    critical_windows = [window for window in schedule["change_windows"] if window["critical"]]
    if critical_windows:
        actions.append(
            "Prioritize critical-path changes: "
            + ", ".join(f"{window['summary']} ({window['build_window']})" for window in critical_windows)
            + "."
        )
    if impact["over_budget"]:
        actions.append("Escalate budget approval before implementation because projected actual exceeds allotment.")
    else:
        actions.append("Track contingency use during implementation; projected actual remains within allotment.")
    if analysis.risks:
        actions.append(f"Resolve listed risk(s): {', '.join(_strip_trailing_punctuation(risk) for risk in analysis.risks)}.")
    return actions


def _build_report_sections(
    analysis: RevisionAnalysis,
    impact: Mapping[str, Any],
    schedule: Mapping[str, Any],
    insights: Mapping[str, Any],
    primary_window: Mapping[str, Any] | None,
    risk_level: str,
) -> list[dict[str, Any]]:
    return [
        {
            "id": "what_changed",
            "title": "What Changed",
            "summary": _what_changed_summary(analysis),
        },
        {
            "id": "what_happens_next",
            "title": "What Happens Next",
            "summary": _what_happens_next_summary(schedule, primary_window),
        },
        {
            "id": "prediction",
            "title": "Prediction",
            "summary": (
                f"Delivery risk is {risk_level}. Budget exposure is {impact['budget_at_risk']}; "
                f"highest cost trade is {insights['highest_cost_trade'] or 'none'}."
            ),
        },
        {
            "id": "schedule",
            "title": "Schedule Impact",
            "summary": _schedule_summary(schedule),
        },
    ]


def _what_changed_summary(analysis: RevisionAnalysis) -> str:
    if not analysis.changes:
        return "No changes were detected."
    categories = sorted({change.category for change in analysis.changes})
    return f"{len(analysis.changes)} change(s) detected across: {', '.join(categories)}."


def _what_happens_next_summary(schedule: Mapping[str, Any], primary_window: Mapping[str, Any] | None) -> str:
    if primary_window is None:
        return "No build sequence was generated."
    return (
        f"Start with {primary_window['task_names'][0]} and complete "
        f"{primary_window['summary']} by {primary_window['build_window']}."
    )


def _schedule_summary(schedule: Mapping[str, Any]) -> str:
    duration_change = schedule["duration_change"]
    if duration_change["baseline_duration_days"] is None:
        return f"Revision work is modeled at {schedule['project_duration_days']} day(s)."
    if duration_change["days_added"]:
        return (
            f"Revision work is modeled at {schedule['project_duration_days']} day(s), "
            f"adding {duration_change['days_added']} day(s) versus baseline."
        )
    if duration_change["days_reduced"]:
        return (
            f"Revision work is modeled at {schedule['project_duration_days']} day(s), "
            f"reducing {duration_change['days_reduced']} day(s) versus baseline."
        )
    return f"Revision work matches the {duration_change['baseline_duration_days']} day baseline."


def _strip_trailing_punctuation(value: str) -> str:
    return value.rstrip(" .")
