from __future__ import annotations

from pathlib import Path

from PIL import Image

from arkirev.annotations import annotate_revised_plan


def test_annotate_revised_plan_draws_bbox_and_saves_output(tmp_path: Path) -> None:
    source = Image.new("RGB", (240, 160), "white")
    analysis = {
        "changes": [
            {
                "summary": "Move bedroom door",
                "category": "door_move",
                "trade": "carpentry",
                "bbox": [40, 50, 70, 40],
            }
        ]
    }
    output_path = tmp_path / "annotated.png"

    annotated = annotate_revised_plan(source, analysis, output_path)

    assert annotated.size == (240, 160)
    assert output_path.exists()
    assert annotated.getpixel((40, 50)) != (255, 255, 255)
    assert Image.open(output_path).size == (240, 160)
