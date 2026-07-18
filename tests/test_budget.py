from __future__ import annotations

import json
from pathlib import Path

import pytest

from arkirev.budget import estimate_impact, load_budget
from arkirev.models import ChangeItem, RevisionAnalysis


def test_load_budget_validates_json() -> None:
    budget = load_budget(Path("data/project_budget.json"))

    assert budget["project_name"] == "Demo House - Phase 1"
    assert budget.unit_costs["door_move"] == 12000


def test_load_budget_rejects_malformed_json(tmp_path: Path) -> None:
    budget_path = tmp_path / "bad_budget.json"
    budget_path.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid budget JSON"):
        load_budget(budget_path)


def test_budget_aggregates_category_costs_by_trade() -> None:
    analysis = RevisionAnalysis(
        changes=[
            ChangeItem(summary="Move bedroom door", category="door_move", trade="carpentry"),
            ChangeItem(summary="Add kitchen opening", category="new_opening", trade="structural"),
            ChangeItem(summary="Widen service opening", category="new_opening", trade="structural"),
        ]
    )

    impact = estimate_impact(analysis, load_budget(Path("data/project_budget.json")))

    assert impact["budget_at_risk"] == 82000
    assert impact["contingency"] == 8200
    assert impact["projected_actual"] == 410200
    assert impact["remaining_allotment"] == 589800
    assert impact["over_budget"] is False
    assert impact["by_trade"] == {"carpentry": 12000, "structural": 70000}
    assert impact["line_items"][0]["category"] == "door_move"


def test_budget_accepts_mapping_inputs_and_flags_over_budget() -> None:
    analysis = {
        "changes": [
            {"summary": "Large layout shift", "category": "layout_change", "trade": "general"},
        ],
    }
    budget = {
        "project_name": "Tiny job",
        "currency": "PHP",
        "allotted_budget": 10000,
        "actual_spent": 9000,
        "contingency_pct": 10,
        "unit_costs": {"layout_change": 25000},
    }

    impact = estimate_impact(analysis, budget)

    assert impact["projected_actual"] == 36500
    assert impact["remaining_allotment"] == -26500
    assert impact["over_budget"] is True


def test_budget_rejects_missing_unit_cost() -> None:
    analysis = RevisionAnalysis(changes=[ChangeItem(summary="Move door", category="door_move")])
    budget = {
        "project_name": "No doors",
        "currency": "PHP",
        "allotted_budget": 100000,
        "actual_spent": 10000,
        "contingency_pct": 0,
        "unit_costs": {"unknown_change": 1000},
    }

    with pytest.raises(ValueError, match="No unit cost configured"):
        estimate_impact(analysis, budget)


def test_budget_rejects_negative_cost(tmp_path: Path) -> None:
    budget_path = tmp_path / "budget.json"
    budget_path.write_text(
        json.dumps(
            {
                "project_name": "Bad cost",
                "currency": "PHP",
                "allotted_budget": 100000,
                "actual_spent": 10000,
                "contingency_pct": 0,
                "unit_costs": {"door_move": -1},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Invalid budget data"):
        load_budget(budget_path)
