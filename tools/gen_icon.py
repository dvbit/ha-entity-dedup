"""Draw the integration icon: two overlapping entity cards merging into one.

Run: python tools/gen_icon.py  → brand/ icons and root icon.png
"""

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
BRAND = ROOT / "custom_components" / "entity_dedup" / "brand"


def draw(size: int) -> Image.Image:
    s = size / 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = int(22 * s)
    # Back card (the orphan duplicate), faded.
    d.rounded_rectangle(
        [int(30 * s), int(30 * s), int(170 * s), int(170 * s)],
        r,
        fill=(3, 169, 244, 90),
        outline=(3, 169, 244, 180),
        width=int(6 * s),
    )
    # Front card (the live entity).
    d.rounded_rectangle(
        [int(86 * s), int(86 * s), int(226 * s), int(226 * s)], r, fill=(3, 169, 244, 255)
    )
    # Merge arrow: from back card corner into front card.
    w = int(14 * s)
    d.line(
        [(int(70 * s), int(70 * s)), (int(150 * s), int(150 * s))],
        fill=(255, 255, 255, 255),
        width=w,
    )
    d.polygon(
        [(int(165 * s), int(165 * s)), (int(112 * s), int(150 * s)), (int(150 * s), int(112 * s))],
        fill=(255, 255, 255, 255),
    )
    # "1" bar: one entity left.
    d.rounded_rectangle(
        [int(180 * s), int(118 * s), int(200 * s), int(200 * s)],
        int(6 * s),
        fill=(255, 255, 255, 255),
    )
    return img


BRAND.mkdir(parents=True, exist_ok=True)
draw(256).save(BRAND / "icon.png")
draw(512).save(BRAND / "icon@2x.png")
draw(256).save(ROOT / "icon.png")
print("icons written")
