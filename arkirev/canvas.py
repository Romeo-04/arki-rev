"""Convert drawable-canvas rectangles into the frozen ChangeItem shape."""
from __future__ import annotations

from typing import Any


def rectangles_to_changes(
    objects: list[dict[str, Any]] | None,
    labels: list[dict[str, str]],
    coordinate_scale: tuple[float, float] = (1.0, 1.0),
) -> list[dict[str, Any]]:
    """Pair rectangles with labels and return bboxes in source-image pixels.

    ``streamlit-drawable-canvas`` reports coordinates in the displayed canvas
    size. The optional ``coordinate_scale`` lets the app render a smaller plan
    while keeping the frozen ChangeItem bbox useful to downstream consumers.
    Fabric also stores rectangle scale factors separately from width/height, so
    those are folded into the returned dimensions here.
    """
    rectangles = [item for item in (objects or []) if item.get("type") == "rect"]
    scale_x, scale_y = coordinate_scale
    changes: list[dict[str, Any]] = []
    for index, rectangle in enumerate(rectangles):
        label = labels[index] if index < len(labels) else {}
        object_scale_x = float(rectangle.get("scaleX", 1))
        object_scale_y = float(rectangle.get("scaleY", 1))
        changes.append({
            "summary": label.get("summary") or f"Markup {index + 1}",
            "category": label.get("category", "unknown_change"),
            "severity": label.get("severity", "medium"),
            "trade": label.get("trade", "general"),
            "verify_before_build": True,
            "bbox": [
                float(rectangle.get("left", 0)) * scale_x,
                float(rectangle.get("top", 0)) * scale_y,
                abs(float(rectangle.get("width", 0)) * object_scale_x) * scale_x,
                abs(float(rectangle.get("height", 0)) * object_scale_y) * scale_y,
            ],
        })
    return changes
