"""
atlas.media — turn the federal renderings into the two sizes the app uses.

The MPO publishes each project's artist rendering at full resolution: the
Crawford hero is 2.08 MB, and the set is roughly 54 MB. That is neither
committable nor loadable into a map pin, so stage 01 downloads the originals
once into the gitignored `data/raw/media/` and derives two committed variants.

    thumb/   96 px, circular, PNG with alpha — the headpiece inside a map pin
    web/     max 1400 px, JPEG — the native project viewer

Two size choices worth stating, because they look arbitrary otherwise:

  The thumbnail is a real circular crop with transparent corners rather than a
  square behind a CSS `border-radius`. MapLibre markers sit on a globe whose
  background is the map itself, so a square image with rounded corners shows its
  corners against the terrain at certain zooms.

  The web variant is JPEG, not PNG. These are photographic renderings with no
  transparency, and PNG holds them at roughly six times the size for no visible
  gain at display resolution.

Derivation is deterministic: same input bytes give byte-identical output, so a
re-run produces an empty git diff. That is what makes "the scrape is
reproducible" testable rather than aspirational.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PIL import Image, ImageDraw

log = logging.getLogger(__name__)

#: Map-pin headpiece. 96 px covers a 48 px pin at 2× device pixel ratio.
THUMB_PX = 96

#: Project-viewer image. Wide enough for a half-screen panel on a large display.
WEB_MAX_PX = 1400
WEB_QUALITY = 82


def _load(path: Path) -> Image.Image:
    img = Image.open(path)
    # Federal renderings arrive as PNG, occasionally palettised or with an alpha
    # channel. Normalising up front means the two derivations below never have
    # to branch on mode.
    return img.convert("RGBA")


def make_thumb(src: Path, dest: Path, size: int = THUMB_PX) -> Path:
    """
    Square centre-crop, resized, with a circular alpha mask.

    Centre-crop rather than squash: these are composed renderings and the
    subject is central in every one inspected. Squashing to a square would
    distort the skyline.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    img = _load(src)

    side = min(img.size)
    left = (img.width - side) // 2
    top = (img.height - side) // 2
    img = img.crop((left, top, left + side, top + side)).resize(
        (size, size), Image.Resampling.LANCZOS
    )

    # Draw the mask at 4× and downsample, so the circle's edge is antialiased.
    # A mask drawn directly at 96 px has visibly stepped edges against the map.
    mask = Image.new("L", (size * 4, size * 4), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size * 4 - 1, size * 4 - 1), fill=255)
    img.putalpha(mask.resize((size, size), Image.Resampling.LANCZOS))

    img.save(dest, format="PNG", optimize=True)
    return dest


def make_web(src: Path, dest: Path, max_px: int = WEB_MAX_PX) -> Path:
    """Downscale to fit `max_px` on the long edge and save as JPEG."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    img = _load(src)

    if max(img.size) > max_px:
        scale = max_px / max(img.size)
        img = img.resize(
            (round(img.width * scale), round(img.height * scale)),
            Image.Resampling.LANCZOS,
        )

    # Flatten onto white: JPEG has no alpha, and the default composite for an
    # RGBA→RGB convert is black, which haloes any rendering with a soft edge.
    flat = Image.new("RGB", img.size, (255, 255, 255))
    flat.paste(img, mask=img.split()[3])
    flat.save(dest, format="JPEG", quality=WEB_QUALITY, optimize=True, progressive=True)
    return dest


def derive(src: Path, media_root: Path, slug: str, suffix: str = "hero") -> tuple[str, str]:
    """
    Produce both variants for one image.

    Returns the pair of paths as the web app will request them — rooted at
    `/media/`, since `web/public/` is served at the site root.
    """
    thumb_rel = f"media/thumb/{slug}-{suffix}.png"
    web_rel = f"media/web/{slug}-{suffix}.jpg"

    make_thumb(src, media_root.parent / thumb_rel)
    make_web(src, media_root.parent / web_rel)

    log.debug("derived %s -> thumb + web", slug)
    return "/" + thumb_rel, "/" + web_rel
