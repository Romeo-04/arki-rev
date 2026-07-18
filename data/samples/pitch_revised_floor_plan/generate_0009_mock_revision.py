"""Generate a mock revised image and annotated output for archive sample 0000-0009."""
from __future__ import annotations

from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from arkirev.annotations import annotate_revised_plan

SOURCE = ROOT / "archive" / "FloorPlanCAD_YOLOv8_Full" / "images" / "0000-0009.png"
BASE_COPY = Path(__file__).with_name("0000-0009_base_original.png")
REVISED = Path(__file__).with_name("0000-0009_revised_mock.png")
ANNOTATED = Path(__file__).with_name("0000-0009_annotated_demo.png")


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "arial.ttf",
    ):
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def generate_revised() -> list[dict[str, object]]:
    image = Image.open(SOURCE).convert("RGB")
    image.save(BASE_COPY)
    draw = ImageDraw.Draw(image)
    font = _font(14)

    changes: list[dict[str, object]] = [
        {
            "summary": "Revise single door opening and swing",
            "category": "door_move",
            "severity": "medium",
            "trade": "carpentry",
            "verify_before_build": True,
            "bbox": [278.32, 102.13, 316.72, 120.48],
        },
        {
            "summary": "Adjust stair and upper wall clearance",
            "category": "layout_change",
            "severity": "medium",
            "trade": "general",
            "verify_before_build": True,
            "bbox": [100.11, 0.0, 539.89, 139.32],
        },
    ]

    # Mock revision marks. These are intentionally blue/yellow so the red
    # annotation output remains visually distinct.
    draw.rectangle((505, 172, 595, 250), outline="#38bdf8", width=4)
    draw.arc((505, 175, 595, 265), 270, 360, fill="#38bdf8", width=3)
    draw.text((504, 254), "MOCK REV DOOR", fill="#38bdf8", font=font)

    draw.line((96, 0, 168, 145), fill="#facc15", width=4)
    draw.line((168, 145, 206, 145), fill="#facc15", width=4)
    draw.text((188, 18), "MOCK REV CLEARANCE", fill="#facc15", font=font)

    image.save(REVISED)
    return changes


if __name__ == "__main__":
    revision_changes = generate_revised()
    annotate_revised_plan(REVISED, {"changes": revision_changes}, ANNOTATED)
    print(BASE_COPY)
    print(REVISED)
    print(ANNOTATED)
