"""Temporary Person B integration stubs.

Replace these imports with ``arkirev.schedule`` and ``arkirev.budget`` once
Person A's tested engine is merged.  The public return shape mirrors the
frozen contract in the implementation brief.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Task:
    id: str
    name: str
    trade: str
    duration_days: float
    change_index: int
    es: float = 0.0
    ef: float = 0.0
    critical: bool = False


@dataclass
class ScheduleResult:
    tasks: list[Task]
    project_duration_days: float
    critical_path: list[str]


_TASKS: dict[str, list[tuple[str, str, float]]] = {
    "new_opening": [
        ("Structural review", "structural", 1.0),
        ("Mark & protect area", "general", 0.5),
        ("Cut opening", "demolition", 1.0),
        ("Install lintel", "structural", 1.0),
        ("Frame opening", "carpentry", 2.0),
    ],
    "door_move": [
        ("Close old opening", "masonry", 1.0),
        ("Cut new opening", "demolition", 1.0),
        ("Frame & hang door", "carpentry", 1.5),
    ],
    "layout_change": [
        ("Re-layout walls", "general", 1.0),
        ("Build/remove partition", "masonry", 2.0),
    ],
    "dimension_or_note_change": [("Update field drawings", "architecture", 0.25)],
    "equipment_or_fixture_change": [
        ("Confirm spec & MEP rough-in", "mep", 1.0),
        ("Install fixture", "mep", 1.0),
    ],
    "unknown_change": [("Investigate & scope", "general", 0.5)],
}

_UNIT_COSTS = {
    "door_move": 12000,
    "new_opening": 35000,
    "layout_change": 25000,
    "dimension_or_note_change": 5000,
    "equipment_or_fixture_change": 18000,
    "unknown_change": 10000,
}


def load_budget(_path: Any = None) -> dict[str, Any]:
    return {
        "project_name": "Demo House — Phase 1",
        "currency": "PHP",
        "allotted_budget": 1_000_000,
        "actual_spent": 320_000,
        "contingency_pct": 10,
    }


def load_templates(_path: Any = None) -> dict[str, Any]:
    return _TASKS


def build_tasks(analysis: Any, _templates: Any = None) -> dict[str, Task]:
    changes = analysis.get("changes", []) if isinstance(analysis, dict) else analysis.changes
    tasks: dict[str, Task] = {}
    for change_index, change in enumerate(changes):
        category = change.get("category", "unknown_change") if isinstance(change, dict) else change.category
        elapsed = 0.0
        for task_index, (name, trade, duration) in enumerate(_TASKS.get(category, _TASKS["unknown_change"])):
            task_id = f"{change_index}:{task_index}"
            tasks[task_id] = Task(task_id, name, trade, duration, change_index, elapsed, elapsed + duration)
            elapsed += duration
    return tasks


def compute_cpm(tasks: dict[str, Task]) -> ScheduleResult:
    if not tasks:
        return ScheduleResult([], 0.0, [])
    longest_change = max(task.change_index for task in tasks.values())
    totals: dict[int, float] = {}
    for task in tasks.values():
        totals[task.change_index] = max(totals.get(task.change_index, 0.0), task.ef)
    longest_change = max(totals, key=totals.get)
    for task in tasks.values():
        task.critical = task.change_index == longest_change
    critical_path = [task.id for task in tasks.values() if task.critical]
    return ScheduleResult(list(tasks.values()), totals[longest_change], critical_path)


def estimate_impact(analysis: Any, budget: dict[str, Any]) -> dict[str, Any]:
    changes = analysis.get("changes", []) if isinstance(analysis, dict) else analysis.changes
    by_trade: dict[str, float] = {}
    line_items: list[dict[str, Any]] = []
    for change in changes:
        get = change.get if isinstance(change, dict) else lambda key, default=None: getattr(change, key, default)
        category = get("category", "unknown_change")
        trade = get("trade", "general") or "general"
        amount = _UNIT_COSTS.get(category, _UNIT_COSTS["unknown_change"])
        by_trade[trade] = by_trade.get(trade, 0) + amount
        line_items.append({"summary": get("summary", "Unlabelled change"), "category": category, "trade": trade, "amount": amount})
    at_risk = sum(by_trade.values())
    contingency = round(at_risk * budget["contingency_pct"] / 100)
    projected = budget["actual_spent"] + at_risk + contingency
    remaining = budget["allotted_budget"] - projected
    return {
        "budget_at_risk": at_risk, "contingency": contingency,
        "projected_actual": projected, "remaining_allotment": remaining,
        "over_budget": remaining < 0, "by_trade": by_trade, "line_items": line_items,
    }
