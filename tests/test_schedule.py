from __future__ import annotations

from pathlib import Path

import pytest

from arkirev.models import ChangeItem, RevisionAnalysis, Task
from arkirev.schedule import build_tasks, compute_cpm, load_templates


TEMPLATES = load_templates(Path("data/task_templates.json"))


def test_single_change_expands_to_template_chain() -> None:
    analysis = RevisionAnalysis(changes=[ChangeItem(summary="Move bedroom door", category="door_move")])

    tasks = build_tasks(analysis, TEMPLATES)

    assert list(tasks) == ["0:0", "0:1", "0:2"]
    assert tasks["0:0"].predecessors == []
    assert tasks["0:1"].predecessors == ["0:0"]
    assert tasks["0:2"].predecessors == ["0:1"]


def test_single_change_chain_duration_and_critical_path() -> None:
    analysis = RevisionAnalysis(changes=[ChangeItem(summary="Move door", category="door_move")])

    result = compute_cpm(build_tasks(analysis, TEMPLATES))

    assert result.project_duration_days == 3.5
    assert result.critical_path == ["0:0", "0:1", "0:2"]
    assert all(task.critical for task in result.tasks)


def test_parallel_changes_take_the_longer_chain() -> None:
    analysis = RevisionAnalysis(
        changes=[
            ChangeItem(summary="Add kitchen opening", category="new_opening"),
            ChangeItem(summary="Update note", category="dimension_or_note_change"),
        ]
    )

    result = compute_cpm(build_tasks(analysis, TEMPLATES))

    assert result.project_duration_days == 5.5
    note_task = [task for task in result.tasks if task.change_index == 1][0]
    assert note_task.slack == 5.25
    assert note_task.critical is False


def test_compute_cpm_does_not_mutate_input_tasks() -> None:
    tasks = build_tasks(
        RevisionAnalysis(changes=[ChangeItem(summary="Move door", category="door_move")]),
        TEMPLATES,
    )

    result = compute_cpm(tasks)

    assert result.tasks[0].ef == 1
    assert tasks["0:0"].ef == 0
    assert tasks["0:0"].critical is False


def test_cycle_detection_raises_exact_error() -> None:
    tasks = {
        "0:0": Task(id="0:0", name="A", trade="general", duration_days=1, change_index=0, predecessors=["0:1"]),
        "0:1": Task(id="0:1", name="B", trade="general", duration_days=1, change_index=0, predecessors=["0:0"]),
    }

    with pytest.raises(ValueError, match="Cycle detected in task graph"):
        compute_cpm(tasks)


def test_missing_predecessor_raises_clear_error() -> None:
    tasks = {
        "0:0": Task(id="0:0", name="A", trade="general", duration_days=1, change_index=0, predecessors=["missing"]),
    }

    with pytest.raises(ValueError, match="references missing predecessor"):
        compute_cpm(tasks)


def test_missing_category_uses_unknown_change_fallback() -> None:
    analysis = RevisionAnalysis(changes=[ChangeItem(summary="Move door", category="door_move")])
    templates = {
        "unknown_change": [{"name": "Investigate", "trade": "general", "duration_days": 0.5, "after": []}],
    }

    tasks = build_tasks(analysis, templates)

    assert tasks["0:0"].name == "Investigate"


def test_missing_category_without_fallback_raises() -> None:
    analysis = RevisionAnalysis(changes=[ChangeItem(summary="Move door", category="door_move")])

    with pytest.raises(ValueError, match="no unknown_change fallback"):
        build_tasks(analysis, {"new_opening": TEMPLATES["new_opening"]})


def test_template_reference_validation() -> None:
    analysis = RevisionAnalysis(changes=[ChangeItem(summary="Move door", category="door_move")])
    templates = {
        "door_move": [{"name": "Bad task", "trade": "general", "duration_days": 1, "after": [3]}],
        "unknown_change": [{"name": "Fallback", "trade": "general", "duration_days": 1, "after": []}],
    }

    with pytest.raises(ValueError, match="references missing predecessor index"):
        build_tasks(analysis, templates)
