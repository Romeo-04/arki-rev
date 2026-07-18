from __future__ import annotations

FLOOR_PLAN_OBJECT_LABELS = (
    "single door",
    "double door",
    "sliding door",
    "window",
    "bay window",
    "blind window",
    "opening symbol",
    "stair",
    "gas stove",
    "refrigerator",
    "washing machine",
    "sink",
    "bath",
    "toilet",
)

VISION_SYSTEM_PROMPT = """You are ArkiRev's optional revision assistant.
Compare two construction floor-plan images and return strict JSON only.
The JSON must match this shape:
{
  "changes": [
    {
      "summary": "short field-ready summary",
      "category": "one allowed category",
      "severity": "one allowed severity",
      "trade": "one allowed trade",
      "verify_before_build": true,
      "bbox": [left, top, width, height]
    }
  ],
  "field_brief": "brief summary for site review",
  "risks": ["risk text"]
}
Allowed category values: door_move, new_opening, layout_change, dimension_or_note_change, equipment_or_fixture_change, unknown_change.
Allowed severity values: low, medium, high.
Allowed trade values: general, structural, demolition, masonry, carpentry, mep, architecture.
Each category, severity, and trade field must contain exactly one allowed value. Do not combine values with pipes, commas, slashes, or prose.
Use unknown_change when the change is unclear. Do not include markdown unless the caller explicitly asks for it.
"""

VISION_USER_PROMPT = """Compare the approved floor plan with the revised floor plan.
Focus on construction-relevant differences such as doors, windows, openings, stairs, and fixtures.
Known floor-plan object labels from the local archive include: {object_labels}.
Return only a RevisionAnalysis JSON object.
""".format(object_labels=", ".join(FLOOR_PLAN_OBJECT_LABELS))
