#!/usr/bin/env python3
"""One-off generator for the participant-facing link-preview images.

Interview links are shared with *participants*, not researchers, so they must
not unfurl with the marketing card ("Stop guessing what your users want",
public/og-image.png) which speaks to the buyer. This script draws one card per
interview language; the backend picks the right one in
``services/interview_preview.py``.

The output PNGs are committed under ``frontend/public/`` and served as static
assets, so this script only needs to run when the artwork or its copy changes:

    python3 frontend/scripts/generate_og_interview.py

Requires Pillow and macOS system fonts (Helvetica Neue). Colours mirror
og-image.png so both cards read as the same brand.
"""

from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 630
# Diagonal brand gradient, sampled from public/og-image.png.
TOP_LEFT = (67, 105, 245)
BOTTOM_RIGHT = (45, 83, 232)

FONT_BOLD = "/System/Library/Fonts/HelveticaNeue.ttc"
FONT_REGULAR = "/System/Library/Fonts/HelveticaNeue.ttc"
BOLD_INDEX, REGULAR_INDEX = 1, 0

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "public")

# Headline + subline per interview language. No em dashes (see CLAUDE.md).
COPY: dict[str, tuple[str, str]] = {
    "en": (
        "You're invited to a\nvoice interview.",
        "Speak from your browser. No install, no account.",
    ),
    "fr": (
        "Vous êtes invité·e à\nun entretien vocal.",
        "Parlez depuis votre navigateur. Sans installation, sans compte.",
    ),
    "de": (
        "Sie sind zu einem\nSprachinterview eingeladen.",
        "Sprechen Sie direkt im Browser. Ohne Installation, ohne Konto.",
    ),
    "es": (
        "Te invitamos a una\nentrevista de voz.",
        "Habla desde tu navegador. Sin instalación, sin cuenta.",
    ),
    "it": (
        "Sei invitato a\nun'intervista vocale.",
        "Parla dal tuo browser. Senza installazioni, senza account.",
    ),
    "pt": (
        "Está convidado(a) para\numa entrevista de voz.",
        "Fale a partir do seu navegador. Sem instalação, sem conta.",
    ),
}


def _gradient() -> Image.Image:
    """Diagonal two-stop gradient, drawn small then upscaled (fast + smooth)."""
    small = Image.new("RGB", (W // 8, H // 8))
    px = small.load()
    for y in range(small.height):
        for x in range(small.width):
            t = (x / (small.width - 1) + y / (small.height - 1)) / 2
            px[x, y] = tuple(
                round(a + (b - a) * t) for a, b in zip(TOP_LEFT, BOTTOM_RIGHT)
            )
    return small.resize((W, H), Image.LANCZOS)


def _rounded_bar(draw: ImageDraw.ImageDraw, x, y, w, h, fill) -> None:
    draw.rounded_rectangle([x, y, x + w, y + h], radius=w / 2, fill=fill)


def _logo(img: Image.Image) -> None:
    """White rounded tile with three waveform bars, then the wordmark."""
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle([80, 72, 152, 144], radius=18, fill=(255, 255, 255, 255))
    blue = TOP_LEFT + (255,)
    _rounded_bar(d, 101, 100, 8, 16, blue)
    _rounded_bar(d, 112, 92, 8, 32, blue)
    _rounded_bar(d, 123, 98, 8, 20, blue)
    img.alpha_composite(layer)

    ImageDraw.Draw(img).text(
        (176, 90),
        "QualiPulse",
        font=ImageFont.truetype(FONT_BOLD, 42, index=BOLD_INDEX),
        fill=(255, 255, 255, 255),
    )


def _waveform(img: Image.Image) -> None:
    """Faded waveform on the right edge, echoing the marketing card."""
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    bars = [(950, 250, 130), (1000, 190, 250), (1050, 150, 330), (1100, 215, 200)]
    for x, top, height in bars:
        _rounded_bar(d, x, top, 34, height, (255, 255, 255, 46))
    img.alpha_composite(layer)


def _card(lang: str) -> Image.Image:
    headline, subline = COPY[lang]
    img = _gradient().convert("RGBA")
    _waveform(img)
    _logo(img)

    d = ImageDraw.Draw(img)
    # Long headlines (de/pt) get a smaller size so they stay clear of the
    # waveform on the right edge.
    longest = max(len(line) for line in headline.split("\n"))
    size = 84 if longest <= 22 else 74 if longest <= 26 else 64
    d.multiline_text(
        (80, 258),
        headline,
        font=ImageFont.truetype(FONT_BOLD, size, index=BOLD_INDEX),
        fill=(255, 255, 255, 255),
        spacing=16,
    )
    d.text(
        (80, 486),
        subline,
        font=ImageFont.truetype(FONT_REGULAR, 30, index=REGULAR_INDEX),
        fill=(255, 255, 255, 224),
    )
    return img.convert("RGB")


def main() -> None:
    for lang in COPY:
        path = os.path.abspath(os.path.join(OUT_DIR, f"og-interview-{lang}.png"))
        _card(lang).save(path, optimize=True)
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
