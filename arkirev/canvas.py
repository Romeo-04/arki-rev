"""Convert drawable-canvas shapes into the frozen ChangeItem shape."""
from __future__ import annotations

from typing import Any

# Every fabric.js object type we let the user draw — rectangle, ellipse, line —
# still serializes a left/top/width/height/scaleX/scaleY bounding box, so one
# bbox formula covers all of them. "point" markups also come back as tiny
# circles from the canvas component.
SHAPE_TYPES = {"rect", "circle", "line"}


def shapes_to_changes(
    objects: list[dict[str, Any]] | None,
    labels: list[dict[str, str]],
    coordinate_scale: tuple[float, float] = (1.0, 1.0),
) -> list[dict[str, Any]]:
    """Pair drawn shapes with labels and return bboxes in source-image pixels.

    ``streamlit-drawable-canvas`` reports coordinates in the displayed canvas
    size. The optional ``coordinate_scale`` lets the app render a smaller plan
    while keeping the frozen ChangeItem bbox useful to downstream consumers.
    Fabric also stores each shape's scale factors separately from width/height,
    so those are folded into the returned dimensions here.
    """
    shapes = [item for item in (objects or []) if item.get("type") in SHAPE_TYPES]
    scale_x, scale_y = coordinate_scale
    changes: list[dict[str, Any]] = []
    for index, shape in enumerate(shapes):
        label = labels[index] if index < len(labels) else {}
        object_scale_x = float(shape.get("scaleX", 1))
        object_scale_y = float(shape.get("scaleY", 1))
        changes.append({
            "summary": label.get("summary") or f"Markup {index + 1}",
            "category": label.get("category", "unknown_change"),
            "severity": label.get("severity", "medium"),
            "trade": label.get("trade", "general"),
            "verify_before_build": True,
            "bbox": [
                float(shape.get("left", 0)) * scale_x,
                float(shape.get("top", 0)) * scale_y,
                abs(float(shape.get("width", 0)) * object_scale_x) * scale_x,
                abs(float(shape.get("height", 0)) * object_scale_y) * scale_y,
            ],
        })
    return changes


def rescale_drawing(json_data: dict[str, Any] | None, factor: float) -> dict[str, Any] | None:
    """Scale every shape in a canvas snapshot, used to preserve markups across a zoom change.

    ``st_canvas`` only applies a new ``initial_drawing`` on remount, and zoom is
    implemented as a remount (new pixel width/height means fabric.js can't just
    resize in place). Re-seeding the remounted canvas with coordinates scaled by
    the zoom ratio keeps existing shapes where the user drew them instead of
    silently dropping their work.
    """
    if not json_data or not json_data.get("objects"):
        return None
    scaled_objects = []
    for shape in json_data["objects"]:
        scaled = dict(shape)
        for key in ("left", "top"):
            if key in scaled:
                scaled[key] = float(scaled[key]) * factor
        for key in ("scaleX", "scaleY"):
            if key in scaled:
                scaled[key] = float(scaled.get(key, 1)) * factor
        scaled_objects.append(scaled)
    return {**json_data, "objects": scaled_objects}
