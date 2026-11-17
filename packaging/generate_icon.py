"""
Generate placeholder SAM icons (PNG and ICO) for packaging.
Run once during the build process if no hand-crafted icon is present.
Requires: Pillow
"""

from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import os

OUT_DIR = Path(__file__).parent / "assets"
OUT_DIR.mkdir(parents=True, exist_ok=True)

PNG_PATH = OUT_DIR / "sam_icon.png"
ICO_PATH = OUT_DIR / "sam_icon.ico"


def make_icon(size: int = 256) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Dark background circle
    margin = size // 16
    draw.ellipse([margin, margin, size - margin, size - margin], fill=(15, 20, 35, 255))

    # Cyan accent ring
    ring = size // 10
    draw.ellipse([ring, ring, size - ring, size - ring], outline=(0, 200, 255, 255), width=size // 20)

    # Inner glow
    inner = size // 4
    draw.ellipse([inner, inner, size - inner, size - inner], fill=(0, 160, 220, 60))

    # "S" letterform (centered)
    try:
        font_size = size // 2
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except IOError:
            font = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), "S", font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x = (size - tw) // 2 - bbox[0]
        y = (size - th) // 2 - bbox[1]
        draw.text((x, y), "S", fill=(0, 220, 255, 255), font=font)
    except Exception:
        pass

    return img


def generate():
    img = make_icon(256)

    if not PNG_PATH.exists():
        img.save(PNG_PATH, format="PNG")
        print(f"Created: {PNG_PATH}")
    else:
        print(f"Skipped (exists): {PNG_PATH}")

    if not ICO_PATH.exists():
        # ICO needs multiple sizes
        sizes = [16, 32, 48, 64, 128, 256]
        frames = [make_icon(s) for s in sizes]
        frames[0].save(
            ICO_PATH,
            format="ICO",
            sizes=[(s, s) for s in sizes],
            append_images=frames[1:],
        )
        print(f"Created: {ICO_PATH}")
    else:
        print(f"Skipped (exists): {ICO_PATH}")


if __name__ == "__main__":
    generate()
