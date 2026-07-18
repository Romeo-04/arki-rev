from __future__ import annotations

import json
from dataclasses import replace
from heapq import heappop, heappush, heapify
from pathlib import Path
from typing import Any, Mapping

from pydantic import ValidationError

from arkirev.models import RevisionAnalysis, ScheduleResult, Task, TaskTemplate

CRITICAL_TOLERANCE = 1e-9


def load_templates(path: str | Path) -> dict[str, list[TaskTemplate]]:
    """Load and validate task templates from JSON."""
    template_path = Path(path)
    if not template_path.exists():
        raise FileNotFoundError(f"Template file not found: {template_path}")
    try:
        with template_path.open(encoding="utf-8") as template_file:
            payload = json.load(template_file)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid template JSON in {template_path}: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Task templates JSON must be an object")

    templates: dict[str, list[TaskTemplate]] = {}
    try:
        for category, raw_tasks in payload.items():
            if not isinstance(category, str) or not category.strip():
                raise ValueError("Template categories must be non-blank strings")
            if not isinstance(raw_tasks, list) or not raw_tasks:
                raise ValueError(f"Template {category!r} must contain at least one task")
            parsed = [TaskTemplate.model_validate(raw_task) for raw_task in raw_tasks]
            _validate_template_references(category, parsed)
            templates[category] = parsed
    except ValidationError as exc:
        raise ValueError(f"Invalid task template data: {exc}") from exc
    return templates


def build_tasks(
    analysis: RevisionAnalysis | Mapping[str, Any],
    templates: Mapping[str, list[TaskTemplate | Mapping[str, Any]]],
) -> dict[str, Task]:
    """Expand each change into independent construction tasks."""
    revision = _coerce_analysis(analysis)
    parsed_templates = _coerce_templates(templates)
    tasks: dict[str, Task] = {}

    for change_index, change in enumerate(revision.changes):
        template = parsed_templates.get(change.category)
        if template is None:
            template = parsed_templates.get("unknown_change")
        if template is None:
            raise ValueError(f"No template configured for category {change.category!r} and no unknown_change fallback")

        for task_index, template_task in enumerate(template):
            task_id = f"{change_index}:{task_index}"
            predecessors = [f"{change_index}:{after_index}" for after_index in template_task.after]
            tasks[task_id] = Task(
                id=task_id,
                name=template_task.name,
                trade=template_task.trade,
                duration_days=float(template_task.duration_days),
                change_index=change_index,
                predecessors=predecessors,
            )

    return tasks


def compute_cpm(tasks: Mapping[str, Task]) -> ScheduleResult:
    """Compute CPM dates, slack, critical flags, and total project duration."""
    scheduled = _copy_tasks(tasks)
    _validate_task_graph(scheduled)

    successors: dict[str, list[str]] = {task_id: [] for task_id in scheduled}
    indegree: dict[str, int] = {task_id: 0 for task_id in scheduled}
    for task in scheduled.values():
        for predecessor in task.predecessors:
            successors[predecessor].append(task.id)
            indegree[task.id] += 1

    for successor_ids in successors.values():
        successor_ids.sort(key=_task_sort_key)

    topo = _topological_order(indegree, successors, len(scheduled))

    for task_id in topo:
        task = scheduled[task_id]
        task.es = max((scheduled[predecessor].ef for predecessor in task.predecessors), default=0.0)
        task.ef = _round_days(task.es + task.duration_days)

    project_end = _round_days(max((task.ef for task in scheduled.values()), default=0.0))

    for task_id in reversed(topo):
        task = scheduled[task_id]
        task.lf = min((scheduled[successor].ls for successor in successors[task_id]), default=project_end)
        task.ls = _round_days(task.lf - task.duration_days)
        task.slack = _round_days(task.ls - task.es)
        task.critical = abs(task.slack) <= CRITICAL_TOLERANCE

    ordered_tasks = [scheduled[task_id] for task_id in topo]
    critical_path = [task.id for task in ordered_tasks if task.critical]
    return ScheduleResult(
        tasks=ordered_tasks,
        project_duration_days=project_end,
        critical_path=critical_path,
    )


def _coerce_analysis(analysis: RevisionAnalysis | Mapping[str, Any]) -> RevisionAnalysis:
    if isinstance(analysis, RevisionAnalysis):
        return analysis
    try:
        return RevisionAnalysis.model_validate(analysis)
    except ValidationError as exc:
        raise ValueError(f"Invalid revision analysis: {exc}") from exc


def _coerce_templates(templates: Mapping[str, list[TaskTemplate | Mapping[str, Any]]]) -> dict[str, list[TaskTemplate]]:
    parsed: dict[str, list[TaskTemplate]] = {}
    try:
        for category, raw_tasks in templates.items():
            if not isinstance(raw_tasks, list) or not raw_tasks:
                raise ValueError(f"Template {category!r} must contain at least one task")
            parsed_tasks = [
                raw_task if isinstance(raw_task, TaskTemplate) else TaskTemplate.model_validate(raw_task)
                for raw_task in raw_tasks
            ]
            _validate_template_references(category, parsed_tasks)
            parsed[category] = parsed_tasks
    except ValidationError as exc:
        raise ValueError(f"Invalid task template data: {exc}") from exc
    return parsed


def _validate_template_references(category: str, tasks: list[TaskTemplate]) -> None:
    for index, task in enumerate(tasks):
        for predecessor_index in task.after:
            if predecessor_index >= len(tasks):
                raise ValueError(
                    f"Template {category!r} task {index} references missing predecessor index {predecessor_index}"
                )


def _copy_tasks(tasks: Mapping[str, Task]) -> dict[str, Task]:
    copied: dict[str, Task] = {}
    for task_id, task in tasks.items():
        if task_id != task.id:
            raise ValueError(f"Task mapping key {task_id!r} does not match task id {task.id!r}")
        copied[task_id] = replace(task, predecessors=list(task.predecessors))
    return copied


def _validate_task_graph(tasks: Mapping[str, Task]) -> None:
    for task in tasks.values():
        if task.duration_days < 0:
            raise ValueError(f"Task {task.id!r} has negative duration_days")
        for predecessor in task.predecessors:
            if predecessor not in tasks:
                raise ValueError(f"Task {task.id!r} references missing predecessor {predecessor!r}")


def _topological_order(indegree: dict[str, int], successors: dict[str, list[str]], expected_count: int) -> list[str]:
    queue: list[tuple[int, int, str, str]] = [(*_task_sort_key(task_id), task_id) for task_id, degree in indegree.items() if degree == 0]
    heapify(queue)
    topo: list[str] = []

    while queue:
        _, _, _, task_id = heappop(queue)
        topo.append(task_id)
        for successor in successors[task_id]:
            indegree[successor] -= 1
            if indegree[successor] == 0:
                heappush(queue, (*_task_sort_key(successor), successor))

    if len(topo) != expected_count:
        raise ValueError("Cycle detected in task graph")
    return topo


def _task_sort_key(task_id: str) -> tuple[int, int, str]:
    try:
        change_index, task_index = task_id.split(":", maxsplit=1)
        return int(change_index), int(task_index), task_id
    except (ValueError, TypeError):
        return 0, 0, task_id


def _round_days(value: float) -> float:
    return round(value, 6)
