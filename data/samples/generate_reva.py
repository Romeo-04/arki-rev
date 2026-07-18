"""Generate the deterministic sample plan used by the ArkiRev demo."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).with_name("RevA.png")
W, H = 1400, 900
image = Image.new("RGB", (W, H), "#f8f5ee")
draw = ImageDraw.Draw(image)
font = ImageFont.truetype("arial.ttf", 28)
small = ImageFont.truetype("arial.ttf", 18)
bold = ImageFont.truetype("arialbd.ttf", 34)

def line(points, width=8):
    draw.line(points, fill="#25313a", width=width, joint="curve")

def room(box, name):
    draw.rectangle(box, outline="#25313a", width=8)
    left, top, right, bottom = box
    bbox = draw.textbbox((0, 0), name, font=font)
    draw.text(((left + right - (bbox[2]-bbox[0])) / 2, (top + bottom - (bbox[3]-bbox[1])) / 2), name, fill="#25313a", font=font)

draw.text((80, 45), "REV A — APPROVED FLOOR PLAN", fill="#0f766e", font=bold)
draw.text((82, 90), "DEMO HOUSE · SCALE 1:100 · ISSUED FOR CONSTRUCTION", fill="#52616b", font=small)
room((110, 180, 690, 530), "LIVING ROOM")
room((690, 180, 1160, 430), "KITCHEN")
room((690, 430, 1160, 680), "DINING")
room((110, 530, 560, 790), "BEDROOM")
room((560, 530, 820, 790), "BATH")
line([(110, 530), (210, 530)], 8)
draw.arc((160, 480, 310, 630), 180, 270, fill="#25313a", width=4)
line([(690, 180), (690, 270)], 8)
draw.arc((620, 205, 760, 345), 270, 360, fill="#25313a", width=4)
for x, y, label in [(195, 145, "7.2 m"), (815, 145, "5.8 m"), (1200, 275, "3.4 m"), (370, 825, "4.6 m")]:
    draw.text((x, y), label, fill="#52616b", font=small)
draw.rectangle((1040, 735, 1320, 830), outline="#52616b", width=2)
draw.text((1060, 755), "ARKIREV SAMPLE", fill="#25313a", font=small)
draw.text((1060, 785), "Rev A · Approved", fill="#52616b", font=small)
image.save(OUT)
