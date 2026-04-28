#!/usr/bin/env python3
"""
Generate synthetic alcohol label images and paired expected-fields JSON files
for the 8 test scenarios documented in docs/test-data.md.

Images are drawn programmatically with Pillow (PIL.ImageDraw).  They are
NOT photorealistic – they are deterministic, reproducible synthetic labels
designed to exercise every status the verification pipeline can return.

Run from the repo root:
    python scripts/generate_samples.py

Output:
    sample_data/labels/<id>.png
    sample_data/expected_fields/<id>.json
    sample_data/manifest.json
"""

from __future__ import annotations

import json
import math
import os
import random
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Dependency guard
# ---------------------------------------------------------------------------
try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
except ImportError:
    print("Pillow is required: pip install Pillow", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
LABELS_DIR = REPO_ROOT / "sample_data" / "labels"
FIELDS_DIR = REPO_ROOT / "sample_data" / "expected_fields"
MANIFEST_PATH = REPO_ROOT / "sample_data" / "manifest.json"

LABELS_DIR.mkdir(parents=True, exist_ok=True)
FIELDS_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Shared label content (canonical "clean_match" values)
# ---------------------------------------------------------------------------
BRAND_CAPS = "STONE'S THROW WINERY"
BRAND_MIXED = "Stone's Throw Winery"
BRAND_TYPO = "STONE'S THROW WINEERY"   # extra E → fuzzy [85, 95) → Needs Review

CLASS_TYPE = "Cabernet Sauvignon"
ABV_CORRECT = "13.5% Alc./Vol."
ABV_WRONG = "14.5% Alc./Vol."           # abv_mismatch scenario
NET_CONTENTS = "750 mL"
BOTTLER = "Bottled by Stone's Throw Winery, Napa, CA"

GOVERNMENT_WARNING_CORRECT = (
    "GOVERNMENT WARNING: (1) According to the Surgeon General, women should "
    "not drink alcoholic beverages during pregnancy because of the risk of "
    "birth defects. (2) Consumption of alcoholic beverages impairs your "
    "ability to drive a car or operate machinery, and may cause health "
    "problems."
)
GOVERNMENT_WARNING_TITLECASE = (
    "Government Warning: (1) According to the Surgeon General, women should "
    "not drink alcoholic beverages during pregnancy because of the risk of "
    "birth defects. (2) Consumption of alcoholic beverages impairs your "
    "ability to drive a car or operate machinery, and may cause health "
    "problems."
)

# Image dimensions
W, H = 1200, 1600

# ---------------------------------------------------------------------------
# Colour palette (cream background, dark ink)
# ---------------------------------------------------------------------------
BG_COLOR = (252, 248, 240)        # warm cream
BORDER_COLOR = (60, 30, 10)       # dark brown
TITLE_COLOR = (30, 20, 10)        # near-black
TEXT_COLOR = (45, 35, 20)
WARNING_BG = (245, 235, 215)
WARNING_TEXT = (30, 20, 10)
ACCENT_COLOR = (120, 60, 20)      # wine red-brown


# ---------------------------------------------------------------------------
# Font helpers – fall back to default if no TTF is available
# ---------------------------------------------------------------------------
def _load_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    """Load a truetype font, falling back to Pillow's built-in default."""
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf" if bold else
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    # Pillow built-in bitmap font – always available, not scalable
    return ImageFont.load_default()


# ---------------------------------------------------------------------------
# Core label drawing helpers
# ---------------------------------------------------------------------------
def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: Any,
               max_width: int) -> list[str]:
    """Wrap text to fit within max_width pixels."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        test = (current + " " + word).strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _draw_base_label(
    *,
    brand: str,
    class_type: str = CLASS_TYPE,
    abv: str = ABV_CORRECT,
    net_contents: str = NET_CONTENTS,
    bottler: str = BOTTLER,
    include_country: bool = False,
    warning_text: str | None = GOVERNMENT_WARNING_CORRECT,
) -> Image.Image:
    """
    Render a synthetic wine label with all standard regions.

    Returns an RGB PIL Image at (W × H) pixels.
    The layout from top to bottom:
        border frame → brand name → decorative rule → class/type →
        ABV + net contents row → bottler → country (optional) →
        warning box (bottom)
    """
    img = Image.new("RGB", (W, H), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # --- Outer border ---
    border_w = 18
    draw.rectangle(
        [border_w // 2, border_w // 2, W - border_w // 2, H - border_w // 2],
        outline=BORDER_COLOR,
        width=border_w,
    )
    # Inner border (decorative)
    gap = 28
    draw.rectangle(
        [gap, gap, W - gap, H - gap],
        outline=ACCENT_COLOR,
        width=3,
    )

    # Fonts
    font_brand = _load_font(68, bold=True)
    font_class = _load_font(44, bold=False)
    font_detail = _load_font(38, bold=False)
    font_small = _load_font(30, bold=False)
    font_warning_hdr = _load_font(28, bold=True)
    font_warning_body = _load_font(26, bold=False)

    margin = 80
    text_width = W - 2 * margin
    y = 100

    # --- Decorative vineyard illustration placeholder ---
    ellipse_x0, ellipse_y0 = W // 2 - 80, y
    ellipse_x1, ellipse_y1 = W // 2 + 80, y + 100
    draw.ellipse([ellipse_x0, ellipse_y0, ellipse_x1, ellipse_y1],
                 outline=ACCENT_COLOR, width=3)
    # Simple grape cluster hint
    for gx, gy in [(W // 2 - 20, y + 40), (W // 2, y + 35),
                   (W // 2 + 20, y + 40), (W // 2 - 10, y + 60),
                   (W // 2 + 10, y + 60)]:
        draw.ellipse([gx - 8, gy - 8, gx + 8, gy + 8],
                     fill=ACCENT_COLOR)
    y += 130

    # --- Brand name ---
    brand_lines = _wrap_text(draw, brand, font_brand, text_width)
    for line in brand_lines:
        bbox = draw.textbbox((0, 0), line, font=font_brand)
        lw = bbox[2] - bbox[0]
        draw.text(((W - lw) // 2, y), line, fill=TITLE_COLOR, font=font_brand)
        y += bbox[3] - bbox[1] + 8
    y += 10

    # --- Decorative rule ---
    draw.line([(margin, y), (W - margin, y)], fill=ACCENT_COLOR, width=3)
    y += 20

    # --- Class / type ---
    class_lines = _wrap_text(draw, class_type, font_class, text_width)
    for line in class_lines:
        bbox = draw.textbbox((0, 0), line, font=font_class)
        lw = bbox[2] - bbox[0]
        draw.text(((W - lw) // 2, y), line, fill=TEXT_COLOR, font=font_class)
        y += bbox[3] - bbox[1] + 6
    y += 16

    # --- Thin decorative rule ---
    draw.line([(margin + 60, y), (W - margin - 60, y)],
              fill=BORDER_COLOR, width=1)
    y += 20

    # --- ABV + Net Contents (side by side) ---
    abv_bbox = draw.textbbox((0, 0), abv, font=font_detail)
    net_bbox = draw.textbbox((0, 0), net_contents, font=font_detail)
    abv_w = abv_bbox[2] - abv_bbox[0]
    net_w = net_bbox[2] - net_bbox[0]
    total_row = abv_w + 60 + net_w
    row_x = (W - total_row) // 2
    draw.text((row_x, y), abv, fill=TEXT_COLOR, font=font_detail)
    draw.text((row_x + abv_w + 60, y), net_contents, fill=TEXT_COLOR,
              font=font_detail)
    row_h = max(abv_bbox[3] - abv_bbox[1], net_bbox[3] - net_bbox[1])
    y += row_h + 24

    # --- Bottler ---
    bottler_lines = _wrap_text(draw, bottler, font_small, text_width)
    for line in bottler_lines:
        bbox = draw.textbbox((0, 0), line, font=font_small)
        lw = bbox[2] - bbox[0]
        draw.text(((W - lw) // 2, y), line, fill=TEXT_COLOR, font=font_small)
        y += bbox[3] - bbox[1] + 5
    y += 10

    # --- Country of origin (optional) ---
    if include_country:
        country_text = "Product of France"
        bbox = draw.textbbox((0, 0), country_text, font=font_small)
        lw = bbox[2] - bbox[0]
        draw.text(((W - lw) // 2, y), country_text,
                  fill=TEXT_COLOR, font=font_small)
        y += bbox[3] - bbox[1] + 10

    # --- Government Warning ---
    if warning_text:
        warning_y_top = H - 300
        draw.rectangle([margin - 10, warning_y_top - 10,
                         W - margin + 10, H - gap - 10],
                        fill=WARNING_BG, outline=BORDER_COLOR, width=2)

        # Split warning into header and body at first colon+space
        colon_idx = warning_text.find(":")
        if colon_idx != -1:
            header_part = warning_text[: colon_idx + 1]   # "GOVERNMENT WARNING:"
            body_part = warning_text[colon_idx + 1:].strip()
        else:
            header_part = ""
            body_part = warning_text

        wy = warning_y_top + 4
        if header_part:
            hdr_bbox = draw.textbbox((0, 0), header_part, font=font_warning_hdr)
            draw.text((margin, wy), header_part,
                      fill=WARNING_TEXT, font=font_warning_hdr)
            wy += hdr_bbox[3] - hdr_bbox[1] + 4

        # Wrap body text
        body_lines = _wrap_text(
            draw, body_part, font_warning_body, text_width - 20)
        for bline in body_lines:
            draw.text((margin, wy), bline,
                      fill=WARNING_TEXT, font=font_warning_body)
            bb = draw.textbbox((0, 0), bline, font=font_warning_body)
            wy += bb[3] - bb[1] + 3

    return img


def _quantize_png(img: Image.Image) -> Image.Image:
    """Quantize to palette mode for smaller PNG files (target < 200 KB)."""
    return img.quantize(colors=256, method=Image.Quantize.MEDIANCUT)


# ---------------------------------------------------------------------------
# Scenario-specific image generators
# ---------------------------------------------------------------------------
def make_clean_match() -> tuple[Image.Image, dict]:
    img = _draw_base_label(brand=BRAND_CAPS)
    return img, {
        "brand_name": "STONE'S THROW WINERY",
        "class_type": "Cabernet Sauvignon",
        "alcohol_content": "13.5% Alc./Vol.",
        "net_contents": "750 mL",
        "bottler": "Bottled by Stone's Throw Winery, Napa, CA",
        "country_of_origin": None,
        "warning": None,
    }


def make_case_only_brand() -> tuple[Image.Image, dict]:
    # Brand printed in mixed case; expected says all-caps
    img = _draw_base_label(brand=BRAND_MIXED)
    return img, {
        "brand_name": "STONE'S THROW WINERY",
        "class_type": "Cabernet Sauvignon",
        "alcohol_content": "13.5% Alc./Vol.",
        "net_contents": "750 mL",
        "bottler": "Bottled by Stone's Throw Winery, Napa, CA",
        "country_of_origin": None,
        "warning": None,
    }


def make_typo_brand() -> tuple[Image.Image, dict]:
    # "WINEERY" — fuzzy ratio in [85, 95) → Needs Review
    img = _draw_base_label(brand=BRAND_TYPO)
    return img, {
        "brand_name": "STONE'S THROW WINERY",
        "class_type": "Cabernet Sauvignon",
        "alcohol_content": "13.5% Alc./Vol.",
        "net_contents": "750 mL",
        "bottler": "Bottled by Stone's Throw Winery, Napa, CA",
        "country_of_origin": None,
        "warning": None,
    }


def make_abv_mismatch() -> tuple[Image.Image, dict]:
    # Label shows 14.5%; expected is 13.5% → Mismatch
    img = _draw_base_label(brand=BRAND_CAPS, abv=ABV_WRONG)
    return img, {
        "brand_name": "STONE'S THROW WINERY",
        "class_type": "Cabernet Sauvignon",
        "alcohol_content": "13.5% Alc./Vol.",
        "net_contents": "750 mL",
        "bottler": "Bottled by Stone's Throw Winery, Napa, CA",
        "country_of_origin": None,
        "warning": None,
    }


def make_warning_titlecase() -> tuple[Image.Image, dict]:
    # Title-case header → Warning Mismatch
    img = _draw_base_label(
        brand=BRAND_CAPS,
        warning_text=GOVERNMENT_WARNING_TITLECASE,
    )
    return img, {
        "brand_name": "STONE'S THROW WINERY",
        "class_type": "Cabernet Sauvignon",
        "alcohol_content": "13.5% Alc./Vol.",
        "net_contents": "750 mL",
        "bottler": "Bottled by Stone's Throw Winery, Napa, CA",
        "country_of_origin": None,
        "warning": None,
    }


def make_warning_missing() -> tuple[Image.Image, dict]:
    # No warning text on label at all
    img = _draw_base_label(brand=BRAND_CAPS, warning_text=None)
    return img, {
        "brand_name": "STONE'S THROW WINERY",
        "class_type": "Cabernet Sauvignon",
        "alcohol_content": "13.5% Alc./Vol.",
        "net_contents": "750 mL",
        "bottler": "Bottled by Stone's Throw Winery, Napa, CA",
        "country_of_origin": None,
        "warning": None,
    }


def make_skewed_lowlight() -> tuple[Image.Image, dict]:
    """
    Clean-match content, then degraded:
      - rotate 7 degrees
      - multiply pixel values by 0.6 then add 30  (reduce contrast)
      - Gaussian blur radius 2
      - slight Gaussian noise
    """
    import numpy as np

    img = _draw_base_label(brand=BRAND_CAPS)

    # Rotate 7 degrees (expand=False keeps size; bg fill = BG_COLOR)
    img = img.rotate(7, resample=Image.BICUBIC, expand=False, fillcolor=BG_COLOR)

    # Reduce contrast: multiply by 0.6 + add 30
    arr = np.array(img, dtype=np.float32)
    arr = arr * 0.6 + 30.0
    arr = np.clip(arr, 0, 255)

    # Skip Gaussian noise entirely. The contrast reduction + heavy blur is
    # what actually drives the reduced-clarity OCR-confidence demo; adding
    # per-pixel noise just defeats PNG compression. We keep the array as-is
    # after the 0.6x + 30 contrast reduction.
    arr = arr.astype(np.uint8)
    img = Image.fromarray(arr)

    # Heavy Gaussian blur to simulate out-of-focus low-light capture.
    img = img.filter(ImageFilter.GaussianBlur(radius=3))

    # Downsample to ~800px wide. The blurred low-light result still has many
    # subtle gradients that don't compress well at 1200x1600; halving the
    # linear dimensions plus aggressive 64-color quantization at save time
    # keeps the file under the HF Spaces 200 KB threshold while preserving
    # more than enough detail for PaddleOCR to demonstrate the
    # reduced-clarity confidence propagation behavior.
    target_w = 800
    target_h = int(H * (target_w / W))
    img = img.resize((target_w, target_h), Image.LANCZOS)

    # Pre-quantize to 64 colors here (instead of relying on the default
    # 256-color quantize step) so that gradients from the rotation fill and
    # blurred body collapse into a small palette and PNG-DEFLATE well.
    img = img.quantize(colors=64, method=Image.Quantize.MEDIANCUT).convert("RGB")

    return img, {
        "brand_name": "STONE'S THROW WINERY",
        "class_type": "Cabernet Sauvignon",
        "alcohol_content": "13.5% Alc./Vol.",
        "net_contents": "750 mL",
        "bottler": "Bottled by Stone's Throw Winery, Napa, CA",
        "country_of_origin": None,
        "warning": None,
    }


def make_unreadable() -> tuple[Image.Image, dict]:
    """
    Nearly-black image (overall pixel mean < 30).
    A faint suggestion of text to satisfy the 'not completely empty' heuristic.
    """
    img = Image.new("RGB", (W, H), (8, 5, 5))
    draw = ImageDraw.Draw(img)

    # Faint text — barely visible, enough to hint there was content
    font = _load_font(40, bold=False)
    # Draw near-black text (colour ~20) on ~8 background
    for i, line in enumerate(["LABEL", "CONTENT", "UNREADABLE"]):
        bbox = draw.textbbox((0, 0), line, font=font)
        lw = bbox[2] - bbox[0]
        draw.text(
            ((W - lw) // 2, 500 + i * 80),
            line,
            fill=(20, 18, 18),
            font=font,
        )

    return img, {
        "brand_name": "STONE'S THROW WINERY",
        "class_type": "Cabernet Sauvignon",
        "alcohol_content": "13.5% Alc./Vol.",
        "net_contents": "750 mL",
        "bottler": "Bottled by Stone's Throw Winery, Napa, CA",
        "country_of_origin": None,
        "warning": None,
    }


# ---------------------------------------------------------------------------
# Scenario registry
# ---------------------------------------------------------------------------
SCENARIOS: list[dict] = [
    {
        "id": "clean_match",
        "title": "Clean match",
        "description": "All standard fields match exactly. High-contrast label with correct Government Warning.",
        "expected_outcome": "All fields Match",
        "provenance": "synthetic",
        "source_url": None,
        "make": make_clean_match,
    },
    {
        "id": "case_only_brand",
        "title": "Brand name \u2014 case only",
        "description": "Brand is printed in mixed case; expected value is all-caps. Normalized comparison returns Match.",
        "expected_outcome": "Brand Match (normalized), others Match",
        "provenance": "synthetic",
        "source_url": None,
        "make": make_case_only_brand,
    },
    {
        "id": "typo_brand",
        "title": "Brand name \u2014 single typo",
        "description": "Brand has an extra character ('WINEERY'). Fuzzy match score falls in the Needs Review range.",
        "expected_outcome": "Brand Needs Review",
        "provenance": "synthetic",
        "source_url": None,
        "make": make_typo_brand,
    },
    {
        "id": "abv_mismatch",
        "title": "ABV mismatch",
        "description": "Label shows 14.5% ABV but the application expects 13.5%. Structured-field comparison returns Mismatch.",
        "expected_outcome": "ABV Mismatch, others Match",
        "provenance": "synthetic",
        "source_url": None,
        "make": make_abv_mismatch,
    },
    {
        "id": "warning_titlecase",
        "title": "Government Warning \u2014 title-case header",
        "description": "Warning header reads 'Government Warning:' instead of the required 'GOVERNMENT WARNING:'. Dedicated validator returns Mismatch.",
        "expected_outcome": "Warning Mismatch",
        "provenance": "synthetic",
        "source_url": None,
        "make": make_warning_titlecase,
    },
    {
        "id": "warning_missing",
        "title": "Government Warning \u2014 missing",
        "description": "No Government Warning statement appears on the label. Validator returns Missing.",
        "expected_outcome": "Warning Missing",
        "provenance": "synthetic",
        "source_url": None,
        "make": make_warning_missing,
    },
    {
        "id": "skewed_lowlight",
        "title": "Skewed / poorly lit photo",
        "description": "Clean-match content rendered with rotation, contrast reduction, blur, and noise. OCR confidence propagates as Needs Review or Uncertain for several fields.",
        "expected_outcome": "Several fields Needs Review or Uncertain",
        "provenance": "synthetic",
        "source_url": None,
        "make": make_skewed_lowlight,
    },
    {
        "id": "unreadable",
        "title": "Unreadable image",
        "description": "Nearly-black image. The preprocessing stage classifies it as FAILED and all fields return Uncertain.",
        "expected_outcome": "All fields Uncertain",
        "provenance": "synthetic",
        "source_url": None,
        "make": make_unreadable,
    },
]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    manifest: list[dict] = []

    for scenario in SCENARIOS:
        sid = scenario["id"]
        print(f"  Generating {sid} …", end=" ", flush=True)

        make_fn = scenario["make"]
        img, expected_fields = make_fn()

        # Save label PNG
        label_path = LABELS_DIR / f"{sid}.png"
        # Quantize for size savings where possible (not for unreadable — already tiny)
        if sid != "unreadable":
            try:
                q = _quantize_png(img)
                q.save(label_path, format="PNG", optimize=True)
                size_kb = label_path.stat().st_size // 1024
                if size_kb > 200:
                    # Fall back to full RGB if quantized is somehow larger
                    img.save(label_path, format="PNG", optimize=True)
            except Exception:
                img.save(label_path, format="PNG", optimize=True)
        else:
            img.save(label_path, format="PNG", optimize=True)

        size_kb = label_path.stat().st_size // 1024
        print(f"label {size_kb} KB", end=" ")

        # Save expected fields JSON
        fields_path = FIELDS_DIR / f"{sid}.json"
        fields_path.write_text(
            json.dumps(expected_fields, indent=2, ensure_ascii=False) + "\n"
        )

        manifest.append(
            {
                "id": sid,
                "title": scenario["title"],
                "description": scenario["description"],
                "expected_outcome": scenario["expected_outcome"],
                "image_path": f"labels/{sid}.png",
                "expected_fields_path": f"expected_fields/{sid}.json",
                "provenance": scenario.get("provenance", "synthetic"),
                "source_url": scenario.get("source_url", None),
            }
        )

        print("✓")

    # Preserve any non-synthetic (e.g. ttb-public) entries already present in
    # the manifest. The TTB reference labels are not generated by this script
    # — they were extracted from public TTB BAM PDFs by a separate one-off
    # step and committed alongside their expected_fields JSON. Re-running the
    # synthetic generator must not silently drop them.
    if MANIFEST_PATH.exists():
        try:
            existing = json.loads(MANIFEST_PATH.read_text())
            synthetic_ids = {s["id"] for s in manifest}
            for entry in existing:
                if (
                    entry.get("provenance") not in {"synthetic", None}
                    and entry.get("id") not in synthetic_ids
                ):
                    manifest.append(entry)
                    print(f"  Preserved external entry: {entry['id']}")
        except (json.JSONDecodeError, KeyError, TypeError):
            # Malformed existing manifest; safe to overwrite with synthetic-only.
            pass

    # Save manifest
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    )
    print(f"\nManifest written → {MANIFEST_PATH}")
    print(f"Labels directory  → {LABELS_DIR}")
    print(f"Fields directory  → {FIELDS_DIR}")


if __name__ == "__main__":
    main()
