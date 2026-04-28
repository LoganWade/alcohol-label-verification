"""One-off helper: downscale and quantize the TTB reference PNGs.

The three TTB-public reference labels were extracted from TTB BAM PDFs by an
earlier samples step and saved at full PDF rendering resolution (~300-450KB
each). Hugging Face Spaces' Git LFS auto-bootstrap rejects PNGs above ~300KB,
so we shrink them in place to <=1200px on the long edge and quantize to a
256-color palette. The visual content remains legible and OCR-quality is
preserved well enough for the demo flow (these are reference cards, not
inputs for OCR scoring).

Idempotent: re-running this script on already-shrunk files is a no-op other
than re-encoding.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
LABELS_DIR = REPO_ROOT / "sample_data" / "labels"

TTB_REFERENCES = (
    "ttb_wine_reference.png",
    "ttb_table_wine_reference.png",
    "ttb_beer_reference.png",
)

MAX_LONG_EDGE = 1200
PALETTE_COLORS = 256


def shrink(path: Path) -> tuple[int, int]:
    """Shrink + quantize a PNG in place. Returns (size_before, size_after)."""
    size_before = path.stat().st_size
    with Image.open(path) as img:
        img = img.convert("RGB")
        # Pillow's thumbnail() preserves aspect ratio and only shrinks (never enlarges).
        img.thumbnail((MAX_LONG_EDGE, MAX_LONG_EDGE), Image.Resampling.LANCZOS)
        # Quantize to a 256-color palette to drastically reduce PNG size while
        # keeping text crisp (palette PNGs compress far better than RGB PNGs).
        quantized = img.quantize(colors=PALETTE_COLORS, method=Image.Quantize.MEDIANCUT)
        quantized.save(path, format="PNG", optimize=True)
    size_after = path.stat().st_size
    return size_before, size_after


def main() -> None:
    print(f"Shrinking TTB reference labels in {LABELS_DIR}")
    for filename in TTB_REFERENCES:
        path = LABELS_DIR / filename
        if not path.exists():
            print(f"  SKIP {filename} (not found)")
            continue
        before, after = shrink(path)
        pct = 100.0 * (1 - after / before) if before else 0.0
        print(
            f"  {filename}: {before/1024:7.1f} KB -> {after/1024:7.1f} KB "
            f"({pct:5.1f}% smaller)"
        )


if __name__ == "__main__":
    main()
