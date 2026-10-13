#!/usr/bin/env python3
"""iPhone screen for the RuntimeBrief Siri demo.

The phone is the captured fictional-demo list. Siri's orb is taken from a
real iPhone frame. The bubble text is the shortcut dialog with the
"Fictional demo." prefix removed. Edit BEATS, then run this file.
"""

from pathlib import Path
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent
BASE_PATH = ROOT / "screens" / "app.png"
SIRI_PATH = ROOT / "screens" / "siri.png"
OUT = ROOT / "runtimebrief-siri-demo.mp4"
POSTER = ROOT / "poster.png"
SANS = "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"
BOLD = "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"

# Spoken lines. Do not put the "Fictional demo." prefix back on these.
BEATS = [
    (3.0, None),
    (4.0, ("What needs attention in RuntimeBrief?", True)),
    (5.0, ("1 project needs attention. Catalog Builder: A fictional copy decision needs attention.", False)),
    (4.0, ("What's the status of Sample Tracker in RuntimeBrief?", True)),
    (8.0, ("Sample Tracker, analyzed just now. This fictional project is ready for review. Its export work is complete, all 24 demo checks pass, and no decision is waiting.", False)),
]


def font(size, bold=False):
    return ImageFont.truetype(BOLD if bold else SANS, size)


def wrap(draw, text, face, width):
    lines, current = [], ""
    for word in text.split():
        trial = word if not current else f"{current} {word}"
        if draw.textlength(trial, font=face) <= width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def orb_sprite(siri_frame):
    # The real sphere from the iPhone capture. Feather only the outer edge.
    center = (589, 2333)
    radius = 112
    pad = 6
    box = (center[0] - radius - pad, center[1] - radius - pad,
           center[0] + radius + pad, center[1] + radius + pad)
    crop = siri_frame.crop(box).convert("RGBA")
    mask = Image.new("L", crop.size, 0)
    inset = pad
    ImageDraw.Draw(mask).ellipse(
        (inset, inset, crop.size[0] - inset - 1, crop.size[1] - inset - 1), fill=255
    )
    mask = mask.filter(ImageFilter.GaussianBlur(0.6))
    crop.putalpha(mask)
    return crop, (box[0], box[1])


def dim(image):
    # Match the dimming measured on the captured Siri frame.
    return ImageEnhance.Brightness(image).enhance(0.80)


def compose(base, orb, orb_at, text):
    image = dim(base)
    draw = ImageDraw.Draw(image)
    width, _height = image.size
    face = font(54, bold=True)
    margin = 42
    max_text = width - margin * 2 - 88
    lines = wrap(draw, text, face, max_text)
    line_h = 68
    text_h = line_h * len(lines)
    pill_h = text_h + 72
    pill_top = orb_at[1] - 36 - pill_h
    pill = (margin, pill_top, width - margin, pill_top + pill_h)
    radius = min(78, pill_h // 2)
    shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        (pill[0], pill[1] + 8, pill[2], pill[3] + 16), radius=radius, fill=(0, 0, 0, 55)
    )
    image = Image.alpha_composite(image, shadow.filter(ImageFilter.GaussianBlur(10)))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(pill, radius=radius, fill=(255, 255, 255, 255))
    y = pill_top + 36
    for line in lines:
        line_w = draw.textlength(line, font=face)
        x = margin + ((width - margin * 2) - line_w) / 2
        draw.text((x, y), line, fill=(0, 0, 0, 255), font=face)
        y += line_h
    image.alpha_composite(orb, orb_at)
    return image.convert("RGB")


def spoken_lines():
    return [payload[0] for _seconds, payload in BEATS if payload]


def main():
    base = Image.open(BASE_PATH).convert("RGBA")
    siri_frame = Image.open(SIRI_PATH).convert("RGBA")
    orb, orb_at = orb_sprite(siri_frame)
    fps = 10
    frames = []
    app = base.convert("RGB")
    for seconds, payload in BEATS:
        count = int(seconds * fps)
        still = app if payload is None else compose(base, orb, orb_at, payload[0])
        frames.extend([still] * count)
    frames[int(7.2 * fps)].save(POSTER, optimize=True)
    with tempfile.TemporaryDirectory(prefix="iphone-siri-") as directory:
        temp = Path(directory)
        for i, still in enumerate(frames):
            still.save(temp / f"frame-{i:04d}.png")
        subprocess.run(
            [
                "ffmpeg", "-v", "error", "-y", "-framerate", str(fps),
                "-i", str(temp / "frame-%04d.png"),
                "-vf", "scale=786:1704",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-crf", "18", "-preset", "fast",
                "-movflags", "+faststart", str(OUT),
            ],
            check=True,
        )


if __name__ == "__main__":
    main()
