"""Field extraction stage: OCR tokens -> ExtractedFields.

Phase 1 implements a minimal heuristic that maps the stub OCR tokens into
the ExtractedFields shape. This is enough to wire the analyze endpoint to a
realistic-looking response so the frontend can be built against it.

Phase 2 replaces the heuristic with proper region attribution + structured
parsers (regex anchors for ABV/proof, unit normalization for net contents,
spatial heuristics for brand/class/bottler).
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from app.core.constants import Confidence
from app.schemas.common import OcrToken
from app.schemas.fields import ExtractedField, ExtractedFields, FieldName

# Regex anchors used by the Phase 1 heuristic. Centralized here so Phase 2
# can promote them into a real region-attribution module.
_ABV_PATTERN = re.compile(r"\d+(?:\.\d+)?\s*%\s*Alc", re.IGNORECASE)
_NET_CONTENTS_PATTERN = re.compile(
    r"\d+(?:\.\d+)?\s*(?:mL|ml|L|fl\s*oz)", re.IGNORECASE
)
_WARNING_ANCHOR = "GOVERNMENT WARNING"

# Tokens whose top edge falls within this many pixels of the previous warning
# token's bottom edge are treated as a continuation of the same warning block.
# PaddleOCR returns one token per text line, and the statutory paragraph spans
# 4-5 lines on a typical TTB label. Without this stitching we'd capture only
# the "GOVERNMENT WARNING:" header line and the validator would see a 71%
# wording-similarity score against the expected paragraph -- exactly the
# behavior reported on the skewed_lowlight sample.
# 80 px is generous enough to absorb baseline jitter on rotated/skewed labels
# (where OCR boxes drift vertically) but tight enough to not glom unrelated
# bottom-of-label text (provenance, country of origin, etc.) into the warning.
_WARNING_LINE_GAP_PX = 80


def _confidence_tier(score: float) -> Confidence:
    if score >= 0.90:
        return Confidence.HIGH
    if score >= 0.75:
        return Confidence.MEDIUM
    if score >= 0.50:
        return Confidence.LOW
    return Confidence.UNCERTAIN


def _empty(field: FieldName) -> ExtractedField:
    return ExtractedField(field=field, confidence=Confidence.UNCERTAIN)


def extract_fields(tokens: Sequence[OcrToken]) -> ExtractedFields:
    """Map OCR tokens to the seven supported fields.

    The mapping is deliberately conservative: when a token does not clearly
    match a field anchor, the field is left as ``Uncertain`` rather than
    guessing. This is the AGENTS.md "uncertainty propagates" rule applied at
    the extraction boundary.
    """

    brand = _empty(FieldName.BRAND_NAME)
    class_type = _empty(FieldName.CLASS_TYPE)
    abv = _empty(FieldName.ALCOHOL_CONTENT)
    net_contents = _empty(FieldName.NET_CONTENTS)
    bottler = _empty(FieldName.BOTTLER)
    country = _empty(FieldName.COUNTRY_OF_ORIGIN)
    warning = _empty(FieldName.WARNING)

    # The stub list is sorted top-to-bottom by y-coordinate. We use simple
    # ordinal heuristics here; Phase 2 introduces real spatial reasoning.
    sorted_tokens = sorted(tokens, key=lambda t: (t.bbox.y0, t.bbox.x0))

    # State for stitching multi-line warning text. Once we see the
    # "GOVERNMENT WARNING" anchor, every subsequent token whose top edge is
    # within _WARNING_LINE_GAP_PX of the previous warning token's bottom edge
    # is folded into the warning. We also track the lowest confidence seen
    # across the block so the validator can downgrade if any line was unsure.
    warning_parts: list[str] = []
    warning_bbox = None
    warning_min_confidence: float | None = None
    warning_last_y1: float | None = None

    def _flush_warning() -> None:
        nonlocal warning, warning_parts
        if not warning_parts:
            return
        joined = "\n".join(warning_parts)
        assert warning_bbox is not None
        assert warning_min_confidence is not None
        warning = ExtractedField(
            field=FieldName.WARNING,
            raw_text=joined,
            normalized_text=joined,
            evidence_bbox=warning_bbox,
            confidence=_confidence_tier(warning_min_confidence),
        )

    for token in sorted_tokens:
        text = token.text
        tier = _confidence_tier(token.confidence)

        # Continuation: we're already collecting a warning block and this token
        # is vertically adjacent to the last one we kept.
        if (
            warning_parts
            and warning_last_y1 is not None
            and token.bbox.y0 - warning_last_y1 <= _WARNING_LINE_GAP_PX
        ):
            warning_parts.append(text)
            warning_bbox = warning_bbox.union(token.bbox)  # type: ignore[union-attr]
            warning_min_confidence = min(
                warning_min_confidence,  # type: ignore[type-var]
                token.confidence,
            )
            warning_last_y1 = token.bbox.y1
            continue

        # Anchor: first time we see "GOVERNMENT WARNING". Start collecting.
        if _WARNING_ANCHOR in text.upper() and not warning_parts:
            warning_parts = [text]
            warning_bbox = token.bbox
            warning_min_confidence = token.confidence
            warning_last_y1 = token.bbox.y1
            continue

        if _ABV_PATTERN.search(text) and abv.raw_text is None:
            abv = ExtractedField(
                field=FieldName.ALCOHOL_CONTENT,
                raw_text=text,
                normalized_text=text,
                evidence_bbox=token.bbox,
                confidence=tier,
            )
            continue

        if _NET_CONTENTS_PATTERN.search(text) and net_contents.raw_text is None:
            net_contents = ExtractedField(
                field=FieldName.NET_CONTENTS,
                raw_text=text,
                normalized_text=text,
                evidence_bbox=token.bbox,
                confidence=tier,
            )
            continue

        if "bottled by" in text.lower() and bottler.raw_text is None:
            bottler = ExtractedField(
                field=FieldName.BOTTLER,
                raw_text=text,
                normalized_text=text,
                evidence_bbox=token.bbox,
                confidence=tier,
            )
            continue

        # First unmatched token from the top is treated as the brand;
        # second as the class/type. Naive but adequate for Phase 1 stub.
        if brand.raw_text is None:
            brand = ExtractedField(
                field=FieldName.BRAND_NAME,
                raw_text=text,
                normalized_text=text,
                evidence_bbox=token.bbox,
                confidence=tier,
            )
            continue

        if class_type.raw_text is None:
            class_type = ExtractedField(
                field=FieldName.CLASS_TYPE,
                raw_text=text,
                normalized_text=text,
                evidence_bbox=token.bbox,
                confidence=tier,
            )
            continue

    _flush_warning()

    return ExtractedFields(
        brand_name=brand,
        class_type=class_type,
        alcohol_content=abv,
        net_contents=net_contents,
        bottler=bottler,
        country_of_origin=country,
        warning=warning,
    )
