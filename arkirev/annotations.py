from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from PIL import Image, ImageDraw, ImageFont
from pydantic import ValidationError

from arkirev.models import RevisionAnalysis

ImageInput = str | Path | Image.Image
REVISION_COLOR = "#dc2626"
REVISION_FILL = "#fee2e2"
TEXT_COLOR = "#111827"


def annotate_revised_plan(
    image: ImageInput,
    analysis: RevisionAnalysis | Mapping[str, Any],
    output_path: str | Path | None = None,
) -> Image.Image:
    """Draw detected revision boxes and labels onto a revised floor plan."""
    revision = _coerce_analysis(analysis)
    annotated = _load_image(image).convert("RGB")
    draw = ImageDraw.Draw(annotated)
    font = _font(16)
    small = _font(13)

    for index, change in enumerate(revision.changes, start=1):
        if not change.bbox:
            continue
        left, top, width, height = _clamp_bbox(change.bbox, annotated.size)
        right = left + width
        bottom = top + height
        label = f"REV-{index:02d} {change.category.replace('_', ' ').title()}"

        draw.rectangle((left, top, right, bottom), outline=REVISION_COLOR, width=4)
        label_box = _label_box(draw, label, change.summary, (left, top), font, small, annotated.size)
        draw.rectangle(label_box, fill=REVISION_FILL, outline=REVISION_COLOR, width=2)
        draw.text((label_box[0] + 8, label_box[1] + 5), label, fill=REVISION_COLOR, font=font)
        draw.text((label_box[0] + 8, label_box[1] + 27), _clip_text(change.summary, 46), fill=TEXT_COLOR, font=small)
        draw.line(
            [
                (label_box[0] + 6, label_box[1] + 24),
                (left + width / 2, top + height / 2),
            ],
            fill=REVISION_COLOR,
            width=2,
        )

    if output_path is not None:
        annotated.save(output_path)
    return annotated


def _coerce_analysis(analysis: RevisionAnalysis | Mapping[str, Any]) -> RevisionAnalysis:
    if isinstance(analysis, RevisionAnalysis):
        return analysis
    try:
        return RevisionAnalysis.model_validate(analysis)
    except ValidationError as exc:
        raise ValueError(f"Invalid revision analysis: {exc}") from exc


def _load_image(image: ImageInput) -> Image.Image:
    if isinstance(image, Image.Image):
        return image.copy()
    return Image.open(image)


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


def _clamp_bbox(bbox: list[float], image_size: tuple[int, int]) -> tuple[float, float, float, float]:
    image_width, image_height = image_size
    left = max(0.0, min(float(bbox[0]), image_width))
    top = max(0.0, min(float(bbox[1]), image_height))
    width = max(1.0, min(float(bbox[2]), image_width - left))
    height = max(1.0, min(float(bbox[3]), image_height - top))
    return left, top, width, height


def _label_box(
    draw: ImageDraw.ImageDraw,
    label: str,
    summary: str,
    anchor: tuple[float, float],
    font: ImageFont.ImageFont,
    small: ImageFont.ImageFont,
    image_size: tuple[int, int],
) -> tuple[float, float, float, float]:
    image_width, image_height = image_size
    clipped = _clip_text(summary, 46)
    label_width = max(
        draw.textlength(label, font=font),
        draw.textlength(clipped, font=small),
    )
    box_width = min(max(label_width + 18, 210), image_width)
    box_height = 52
    x = min(max(anchor[0], 0), max(image_width - box_width, 0))
    y = anchor[1] - box_height - 8
    if y < 0:
        y = min(anchor[1] + 8, max(image_height - box_height, 0))
    return (x, y, x + box_width, y + box_height)


def _clip_text(value: str, max_chars: int) -> str:
    text = " ".join(value.split())
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "..."
