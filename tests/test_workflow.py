from __future__ import annotations

from pathlib import Path

import pytest

from arkirev import run_revision_workflow
from arkirev.models import ChangeItem, RevisionAnalysis


def test_workflow_returns_ui_ready_budget_and_schedule_payload() -> None:
    result = run_revision_workflow(
        [
            {"summary": "Add kitchen opening", "category": "new_opening", "trade": "structural"},
            {"summary": "Move bedroom door", "category": "door_move", "trade": "carpentry"},
        ],
        field_brief="Kitchen opening and door move affect structure and carpentry.",
        risks=["Verify lintel sizing."],
    )

    assert result["analysis"]["field_brief"] == "Kitchen opening and door move affect structure and carpentry."
    assert result["analysis"]["risks"] == ["Verify lintel sizing."]
    assert result["budget"]["currency"] == "PHP"
    assert result["impact"]["budget_at_risk"] == 47000
    assert result["impact"]["contingency"] == 4700
    assert result["impact"]["by_trade"] == {"carpentry": 12000, "structural": 35000}
    assert result["schedule"]["project_duration_days"] == 5.5
    assert result["schedule"]["duration_change"] == {
        "baseline_duration_days": None,
        "duration_delta_days": None,
        "days_added": 0.0,
        "days_reduced": 0.0,
    }
    assert result["schedule"]["critical_path"] == ["0:0", "0:1", "0:2", "0:3", "0:4"]
    assert result["schedule"]["tasks"][0]["id"] == "0:0"
    assert result["schedule"]["tasks"][0]["critical"] is True
    assert result["schedule"]["change_windows"][0] == {
        "change_index": 0,
        "summary": "Add kitchen opening",
        "category": "new_opening",
        "trade": "structural",
        "start_day": 0.0,
        "finish_day": 5.5,
        "implementation_days": 5.5,
        "work_days": 5.5,
        "build_window": "Day 0 to Day 5.5",
        "critical": True,
        "controls_project_finish": True,
        "days_added_to_revision": 5.5,
        "days_reduced_from_revision": 0.0,
        "task_ids": ["0:0", "0:1", "0:2", "0:3", "0:4"],
        "task_names": [
            "Structural review",
            "Mark & protect area",
            "Cut opening",
            "Install lintel",
            "Frame opening",
        ],
        "critical_task_ids": ["0:0", "0:1", "0:2", "0:3", "0:4"],
    }
    assert result["schedule"]["change_windows"][1]["build_window"] == "Day 0 to Day 3.5"
    assert result["schedule"]["change_windows"][1]["days_added_to_revision"] == 0.0
    assert result["insights"]["change_count"] == 2
    assert result["insights"]["highest_cost_trade"] == "structural"
    assert result["insights"]["critical_trades"] == [
        "carpentry",
        "demolition",
        "general",
        "structural",
    ]
    assert "47,000" not in result["insights"]["summary"]
    assert "47000 at risk" in result["insights"]["summary"]
    assert result["report"]["title"] == "Revision impact summary"
    assert result["report"]["prediction"]["risk_level"] == "medium"
    assert result["report"]["prediction"]["budget_at_risk"] == 47000
    assert result["report"]["what_changed"][0]["summary"] == "Add kitchen opening"
    assert result["report"]["what_changed"][0]["implementation_window"] == "Day 0 to Day 5.5"
    assert result["report"]["what_changed"][0]["predicted_tasks"] == [
        "Structural review",
        "Mark & protect area",
        "Cut opening",
        "Install lintel",
        "Frame opening",
    ]
    assert result["report"]["implementation_plan"]["overall_window"] == "Day 0 to Day 5.5"
    assert result["report"]["implementation_plan"]["critical_changes"][0]["summary"] == "Add kitchen opening"
    assert result["report"]["sections"][0] == {
        "id": "what_changed",
        "title": "What Changed",
        "summary": "2 change(s) detected across: door_move, new_opening.",
    }
    assert "Expected impact is 47000 at risk" in result["report"]["executive_summary"]
    assert "Verify before build: Add kitchen opening, Move bedroom door." in result["report"]["field_actions"]


def test_workflow_accepts_revision_analysis_model() -> None:
    analysis = RevisionAnalysis(
        changes=[ChangeItem(summary="Update drawing note", category="dimension_or_note_change", trade="architecture")]
    )

    result = run_revision_workflow(analysis)

    assert result["impact"]["budget_at_risk"] == 5000
    assert result["schedule"]["project_duration_days"] == 0.25
    assert result["insights"]["review_required_count"] == 1
    assert result["report"]["cost_prediction"]["budget_at_risk"] == 5000


def test_workflow_reports_days_added_against_baseline() -> None:
    result = run_revision_workflow(
        [{"summary": "Add kitchen opening", "category": "new_opening", "trade": "structural"}],
        baseline_duration_days=4,
    )

    assert result["schedule"]["duration_change"] == {
        "baseline_duration_days": 4,
        "duration_delta_days": 1.5,
        "days_added": 1.5,
        "days_reduced": 0.0,
    }
    assert "adds 1.5 day(s) versus the baseline" in result["insights"]["summary"]
    assert result["report"]["prediction"]["days_added"] == 1.5


def test_workflow_reports_days_reduced_against_baseline() -> None:
    result = run_revision_workflow(
        [{"summary": "Update drawing note", "category": "dimension_or_note_change", "trade": "architecture"}],
        baseline_duration_days=2,
    )

    assert result["schedule"]["duration_change"] == {
        "baseline_duration_days": 2,
        "duration_delta_days": -1.75,
        "days_added": 0.0,
        "days_reduced": 1.75,
    }
    assert "reduces the plan by 1.75 day(s) versus the baseline" in result["insights"]["summary"]
    assert result["report"]["prediction"]["days_reduced"] == 1.75


def test_workflow_insights_handle_empty_dataset_labels() -> None:
    result = run_revision_workflow([])

    assert result["impact"]["budget_at_risk"] == 0
    assert result["schedule"]["project_duration_days"] == 0.0
    assert result["schedule"]["change_windows"] == []
    assert result["insights"]["summary"] == (
        "No structured changes were detected, so there is no added budget or schedule impact."
    )
    assert result["insights"]["critical_trades"] == []
    assert result["report"]["executive_summary"] == "No construction-relevant floor-plan changes were detected."
    assert result["report"]["field_actions"] == [
        "No field action required until a construction-relevant change is identified."
    ]


def test_workflow_surfaces_invalid_change_data() -> None:
    with pytest.raises(ValueError, match="Invalid change data"):
        run_revision_workflow([{"summary": "", "category": "door_move"}])


def test_workflow_surfaces_missing_configuration(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Budget file not found"):
        run_revision_workflow([], budget_path=tmp_path / "missing.json")


def test_workflow_rejects_negative_baseline_duration() -> None:
    with pytest.raises(ValueError, match="baseline_duration_days must be non-negative"):
        run_revision_workflow([], baseline_duration_days=-1)
