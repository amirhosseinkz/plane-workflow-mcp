#!/usr/bin/env python3
"""Render the offline walkthrough as an animated terminal GIF.

uv run --locked --project plugins/plane-workflow --with pillow python scripts/render_demo_gif.py docs/demo.gif
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from demo_walkthrough import walkthrough  # noqa: E402

FONT_CANDIDATES = ["/System/Library/Fonts/Menlo.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"]
SCALE = 2
FONT_SIZE = 14 * SCALE
LINE_HEIGHT = 22 * SCALE
PAD = 24 * SCALE
BAR = 34 * SCALE
WIDTH = 820 * SCALE
COLORS = {
    "bg": "#0d1117",
    "bar": "#161b22",
    "title": "#8b949e",
    "user": "#79c0ff",
    "tool": "#d2a8ff",
    "out": "#e6edf3",
    "ok": "#3fb950",
    "warn": "#d29922",
}
PREFIX = {"user": "> ", "tool": "● ", "out": "  ", "ok": "  ✓ ", "warn": "  ! "}


def _font() -> ImageFont.FreeTypeFont:
    for candidate in FONT_CANDIDATES:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, FONT_SIZE)
    raise SystemExit("No monospace font found; add one to FONT_CANDIDATES.")


def _frame(lines: list[tuple[str, str]], height: int, font: ImageFont.FreeTypeFont, cursor: bool) -> Image.Image:
    image = Image.new("RGB", (WIDTH, height), COLORS["bg"])
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, WIDTH, BAR], fill=COLORS["bar"])
    for index, color in enumerate(("#ff5f56", "#ffbd2e", "#27c93f")):
        x = PAD + index * 20 * SCALE
        draw.ellipse([x, BAR // 2 - 6 * SCALE, x + 12 * SCALE, BAR // 2 + 6 * SCALE], fill=color)
    draw.text((WIDTH // 2, BAR // 2), "plane-workflow · offline demo", fill=COLORS["title"], font=font, anchor="mm")
    y = BAR + PAD
    for kind, text in lines:
        draw.text((PAD, y), PREFIX.get(kind, "") + text, fill=COLORS.get(kind, COLORS["out"]), font=font)
        y += LINE_HEIGHT
    if cursor and lines:
        kind, text = lines[-1]
        x = PAD + draw.textlength(PREFIX.get(kind, "") + text, font=font) + 2 * SCALE
        draw.rectangle([x, y - LINE_HEIGHT + 3 * SCALE, x + 9 * SCALE, y - 5 * SCALE], fill=COLORS["user"])
    return image.resize((WIDTH // SCALE, height // SCALE), Image.LANCZOS)


def render(output: Path) -> None:
    script = walkthrough()
    font = _font()
    height = BAR + PAD * 2 + LINE_HEIGHT * len(script)
    frames: list[Image.Image] = []
    durations: list[int] = []

    def add(lines: list[tuple[str, str]], milliseconds: int, cursor: bool = False) -> None:
        frames.append(_frame(lines, height, font, cursor))
        durations.append(milliseconds)

    shown: list[tuple[str, str]] = []
    for kind, text in script:
        if kind == "user":
            for end in range(0, len(text) + 1, 3):
                add([*shown, (kind, text[:end])], 40, cursor=True)
            shown.append((kind, text))
            add(shown, 700)
        elif kind == "tool":
            shown.append((kind, text))
            add(shown, 900)
        else:
            shown.append((kind, text))
            add(shown, 250 if kind == "out" else 600)
    durations[-1] = 5000
    frames[0].save(output, save_all=True, append_images=frames[1:], duration=durations, loop=0, optimize=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    render(parser.parse_args().output)


if __name__ == "__main__":
    main()
