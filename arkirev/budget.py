from __future__ import annotations

import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Mapping

from pydantic import ValidationError

from arkirev.models import BudgetConfig, BudgetLineItem, RevisionAnalysis


def load_budget(path: str | Path) -> BudgetConfig:
    """Load and validate a project budget JSON file."""
    budget_path = Path(path)
    if not budget_path.exists():
        raise FileNotFoundError(f"Budget file not found: {budget_path}")
    try:
        with budget_path.open(encoding="utf-8") as budget_file:
            payload = json.load(budget_file)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid budget JSON in {budget_path}: {exc.msg}") from exc

    try:
        return BudgetConfig.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"Invalid budget data in {budget_path}: {exc}") from exc


def estimate_impact(analysis: RevisionAnalysis | Mapping[str, Any], budget: BudgetConfig | Mapping[str, Any]) -> dict[str, Any]:
    """Estimate deterministic cost impact for a revision analysis."""
    revision = _coerce_analysis(analysis)
    config = _coerce_budget(budget)

    line_items: list[dict[str, Any]] = []
    by_trade: dict[str, int] = {}
    raw_total = Decimal("0")

    for index, change in enumerate(revision.changes):
        if change.category not in config.unit_costs:
            raise ValueError(f"No unit cost configured for category {change.category!r}")
        amount = _money(config.unit_costs[change.category])
        raw_total += Decimal(amount)
        by_trade[change.trade] = by_trade.get(change.trade, 0) + amount
        item = BudgetLineItem(
            change_index=index,
            summary=change.summary,
            category=change.category,
            trade=change.trade,
            amount=amount,
        )
        line_items.append(item.model_dump())

    budget_at_risk = _money(raw_total)
    contingency = _money(Decimal(budget_at_risk) * Decimal(str(config.contingency_pct)) / Decimal("100"))
    actual_spent = _money(config.actual_spent)
    allotted_budget = _money(config.allotted_budget)
    projected_actual = actual_spent + budget_at_risk + contingency
    remaining_allotment = allotted_budget - projected_actual

    return {
        "budget_at_risk": budget_at_risk,
        "contingency": contingency,
        "projected_actual": projected_actual,
        "remaining_allotment": remaining_allotment,
        "over_budget": projected_actual > allotted_budget,
        "by_trade": dict(sorted(by_trade.items())),
        "line_items": line_items,
    }


def _coerce_analysis(analysis: RevisionAnalysis | Mapping[str, Any]) -> RevisionAnalysis:
    if isinstance(analysis, RevisionAnalysis):
        return analysis
    try:
        return RevisionAnalysis.model_validate(analysis)
    except ValidationError as exc:
        raise ValueError(f"Invalid revision analysis: {exc}") from exc


def _coerce_budget(budget: BudgetConfig | Mapping[str, Any]) -> BudgetConfig:
    if isinstance(budget, BudgetConfig):
        return budget
    try:
        return BudgetConfig.model_validate(budget)
    except ValidationError as exc:
        raise ValueError(f"Invalid budget data: {exc}") from exc


def _money(value: int | float | Decimal) -> int:
    decimal_value = Decimal(str(value))
    if decimal_value < 0:
        raise ValueError("monetary values must be non-negative")
    return int(decimal_value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
