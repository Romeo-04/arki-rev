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
    assert result["schedule"]["critical_path"] == ["0:0", "0:1", "0:2", "0:3", "0:4"]
    assert result["schedule"]["tasks"][0]["id"] == "0:0"
    assert result["schedule"]["tasks"][0]["critical"] is True
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


def test_workflow_accepts_revision_analysis_model() -> None:
    analysis = RevisionAnalysis(
        changes=[ChangeItem(summary="Update drawing note", category="dimension_or_note_change", trade="architecture")]
    )

    result = run_revision_workflow(analysis)

    assert result["impact"]["budget_at_risk"] == 5000
    assert result["schedule"]["project_duration_days"] == 0.25
    assert result["insights"]["review_required_count"] == 1


def test_workflow_insights_handle_empty_dataset_labels() -> None:
    result = run_revision_workflow([])

    assert result["impact"]["budget_at_risk"] == 0
    assert result["schedule"]["project_duration_days"] == 0.0
    assert result["insights"]["summary"] == (
        "No structured changes were detected, so there is no added budget or schedule impact."
    )
    assert result["insights"]["critical_trades"] == []


def test_workflow_surfaces_invalid_change_data() -> None:
    with pytest.raises(ValueError, match="Invalid change data"):
        run_revision_workflow([{"summary": "", "category": "door_move"}])


def test_workflow_surfaces_missing_configuration(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Budget file not found"):
        run_revision_workflow([], budget_path=tmp_path / "missing.json")
