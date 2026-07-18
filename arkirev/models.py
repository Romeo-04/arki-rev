from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator, Literal

from pydantic import BaseModel, Field, field_validator

ChangeCategory = Literal[
    "door_move",
    "new_opening",
    "layout_change",
    "dimension_or_note_change",
    "equipment_or_fixture_change",
    "unknown_change",
]

Severity = Literal["low", "medium", "high"]


class MappingModel(BaseModel):
    """Pydantic model with light dict-style read compatibility."""

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def keys(self) -> Iterator[str]:
        return iter(self.model_fields)

    def items(self) -> Iterator[tuple[str, Any]]:
        for key in self.model_fields:
            yield key, getattr(self, key)


class ChangeItem(MappingModel):
    summary: str
    category: ChangeCategory = "unknown_change"
    severity: Severity = "medium"
    trade: str = "general"
    verify_before_build: bool = True
    bbox: list[float] | None = None

    @field_validator("summary", "trade")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value

    @field_validator("bbox")
    @classmethod
    def _valid_bbox(cls, value: list[float] | None) -> list[float] | None:
        if value is None:
            return value
        if len(value) != 4:
            raise ValueError("bbox must contain [left, top, width, height]")
        if any(v < 0 for v in value):
            raise ValueError("bbox values must be non-negative")
        return value


class RevisionAnalysis(MappingModel):
    changes: list[ChangeItem] = Field(default_factory=list)
    field_brief: str = ""
    risks: list[str] = Field(default_factory=list)


class BudgetConfig(MappingModel):
    project_name: str
    currency: str = "PHP"
    allotted_budget: float
    actual_spent: float
    contingency_pct: float = 0.0
    manual_review_minutes_baseline: int = 30
    unit_costs: dict[str, float]

    @field_validator("project_name", "currency")
    @classmethod
    def _text_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value

    @field_validator("allotted_budget", "actual_spent", "contingency_pct")
    @classmethod
    def _non_negative_number(cls, value: float) -> float:
        if value < 0:
            raise ValueError("numeric budget values must be non-negative")
        return value

    @field_validator("manual_review_minutes_baseline")
    @classmethod
    def _non_negative_minutes(cls, value: int) -> int:
        if value < 0:
            raise ValueError("manual_review_minutes_baseline must be non-negative")
        return value

    @field_validator("unit_costs")
    @classmethod
    def _valid_unit_costs(cls, value: dict[str, float]) -> dict[str, float]:
        if not value:
            raise ValueError("unit_costs must not be empty")
        for category, cost in value.items():
            if not category.strip():
                raise ValueError("unit_costs categories must not be blank")
            if cost < 0:
                raise ValueError(f"unit cost for {category!r} must be non-negative")
        return value


class BudgetLineItem(MappingModel):
    change_index: int
    summary: str
    category: str
    trade: str
    amount: int

    @field_validator("change_index", "amount")
    @classmethod
    def _non_negative_int(cls, value: int) -> int:
        if value < 0:
            raise ValueError("line item numeric values must be non-negative")
        return value


class TaskTemplate(MappingModel):
    name: str
    trade: str
    duration_days: float
    after: list[int] = Field(default_factory=list)

    @field_validator("name", "trade")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value

    @field_validator("duration_days")
    @classmethod
    def _positive_duration(cls, value: float) -> float:
        if value < 0:
            raise ValueError("duration_days must be non-negative")
        return value

    @field_validator("after")
    @classmethod
    def _valid_after(cls, value: list[int]) -> list[int]:
        if any(index < 0 for index in value):
            raise ValueError("after indices must be non-negative")
        return value


@dataclass
class Task:
    id: str
    name: str
    trade: str
    duration_days: float
    change_index: int
    predecessors: list[str] = field(default_factory=list)
    es: float = 0.0
    ef: float = 0.0
    ls: float = 0.0
    lf: float = 0.0
    slack: float = 0.0
    critical: bool = False

    def __post_init__(self) -> None:
        if self.duration_days < 0:
            raise ValueError("duration_days must be non-negative")


@dataclass
class ScheduleResult:
    tasks: list[Task]
    project_duration_days: float
    critical_path: list[str]
