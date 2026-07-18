"""Generate pitch-ready Rev A and revised floor-plan assets."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT_DIR = Path(__file__).resolve().parent
REV_A_PATH = OUT_DIR / "RevA_approved.png"
REV_B_PATH = OUT_DIR / "RevB_revised.png"

W, H = 1400, 900
WALL = "#25313a"
PAPER = "#f8f5ee"
MUTED = "#52616b"
APPROVED = "#0f766e"
REVISION = "#dc2626"
REVISION_FILL = "#fee2e2"
BLUEPRINT = "#2563eb"


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        "arialbd.ttf" if bold else "arial.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


FONT = _font(28)
SMALL = _font(18)
TINY = _font(15)
BOLD = _font(34, bold=True)
LABEL = _font(20, bold=True)


def _line(draw: ImageDraw.ImageDraw, points: list[tuple[int, int]], width: int = 8, fill: str = WALL) -> None:
    draw.line(points, fill=fill, width=width, joint="curve")


def _room(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], name: str) -> None:
    draw.rectangle(box, outline=WALL, width=8)
    left, top, right, bottom = box
    text_box = draw.textbbox((0, 0), name, font=FONT)
    text_width = text_box[2] - text_box[0]
    text_height = text_box[3] - text_box[1]
    draw.text(
        ((left + right - text_width) / 2, (top + bottom - text_height) / 2),
        name,
        fill=WALL,
        font=FONT,
    )


def _revision_callout(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    label: str,
    note: str,
    anchor: tuple[int, int],
) -> None:
    draw.rectangle(box, outline=REVISION, width=5)
    draw.rectangle((anchor[0], anchor[1], anchor[0] + 330, anchor[1] + 64), fill=REVISION_FILL, outline=REVISION, width=3)
    draw.text((anchor[0] + 12, anchor[1] + 8), label, fill=REVISION, font=LABEL)
    draw.text((anchor[0] + 12, anchor[1] + 36), note, fill=WALL, font=TINY)
    draw.line(
        [
            (anchor[0] + 8, anchor[1] + 32),
            ((box[0] + box[2]) // 2, (box[1] + box[3]) // 2),
        ],
        fill=REVISION,
        width=3,
    )


def _draw_base(title: str, subtitle: str) -> Image.Image:
    image = Image.new("RGB", (W, H), PAPER)
    draw = ImageDraw.Draw(image)

    draw.text((80, 45), title, fill=APPROVED, font=BOLD)
    draw.text((82, 90), subtitle, fill=MUTED, font=SMALL)

    _room(draw, (110, 180, 690, 530), "LIVING ROOM")
    _room(draw, (690, 180, 1160, 430), "KITCHEN")
    _room(draw, (690, 430, 1160, 680), "DINING")
    _room(draw, (110, 530, 560, 790), "BEDROOM")
    _room(draw, (560, 530, 820, 790), "BATH")

    _line(draw, [(110, 530), (210, 530)])
    draw.arc((160, 480, 310, 630), 180, 270, fill=WALL, width=4)
    _line(draw, [(690, 180), (690, 270)])
    draw.arc((620, 205, 760, 345), 270, 360, fill=WALL, width=4)

    draw.rectangle((910, 215, 1010, 265), outline=MUTED, width=3)
    draw.text((920, 230), "SINK", fill=MUTED, font=TINY)

    for x, y, label in [(195, 145, "7.2 m"), (815, 145, "5.8 m"), (1200, 275, "3.4 m"), (370, 825, "4.6 m")]:
        draw.text((x, y), label, fill=MUTED, font=SMALL)

    draw.rectangle((1040, 735, 1320, 830), outline=MUTED, width=2)
    draw.text((1060, 755), "ARKIREV SAMPLE", fill=WALL, font=SMALL)
    return image


def generate_rev_a() -> None:
    image = _draw_base("REV A - APPROVED FLOOR PLAN", "DEMO HOUSE | SCALE 1:100 | ISSUED FOR CONSTRUCTION")
    draw = ImageDraw.Draw(image)
    draw.text((1060, 785), "Rev A | Approved", fill=MUTED, font=SMALL)
    image.save(REV_A_PATH)


def generate_rev_b() -> None:
    image = _draw_base("REV B - REVISED FLOOR PLAN", "DEMO HOUSE | REVISION FOR FIELD COORDINATION")
    draw = ImageDraw.Draw(image)

    draw.rectangle((660, 265, 720, 390), fill=PAPER, outline=BLUEPRINT, width=4)
    draw.text((645, 238), "NEW OPENING", fill=BLUEPRINT, font=TINY)

    draw.line([(110, 530), (210, 530)], fill=PAPER, width=12)
    _line(draw, [(285, 530), (385, 530)], fill=WALL)
    draw.arc((335, 480, 485, 630), 180, 270, fill=BLUEPRINT, width=4)
    draw.text((270, 498), "DOOR MOVED", fill=BLUEPRINT, font=TINY)

    draw.rectangle((910, 215, 1010, 265), fill=PAPER, outline=PAPER, width=6)
    draw.rectangle((785, 220, 885, 270), outline=BLUEPRINT, width=3)
    draw.text((795, 235), "SINK", fill=BLUEPRINT, font=TINY)

    _revision_callout(
        draw,
        (640, 260, 730, 380),
        "REV-01 STRUCTURAL",
        "New living-to-kitchen opening",
        (865, 165),
    )
    _revision_callout(
        draw,
        (185, 510, 390, 625),
        "REV-02 CARPENTRY",
        "Bedroom door shifted right",
        (205, 385),
    )
    _revision_callout(
        draw,
        (770, 205, 1015, 285),
        "REV-03 MEP",
        "Kitchen sink rough-in relocated",
        (900, 320),
    )

    draw.text((1060, 785), "Rev B | Revised", fill=REVISION, font=SMALL)
    image.save(REV_B_PATH)


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    generate_rev_a()
    generate_rev_b()
