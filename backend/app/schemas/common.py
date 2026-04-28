"""Common primitives shared across schemas: bounding boxes, OCR tokens."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class BoundingBox(BaseModel):
    """Axis-aligned bounding box in image pixel coordinates.

    Origin is top-left. ``x0, y0`` is the top-left corner; ``x1, y1`` is the
    bottom-right corner.
    """

    model_config = ConfigDict(frozen=True)

    x0: int = Field(ge=0)
    y0: int = Field(ge=0)
    x1: int = Field(ge=0)
    y1: int = Field(ge=0)

    def as_tuple(self) -> tuple[int, int, int, int]:
        return (self.x0, self.y0, self.x1, self.y1)


class OcrToken(BaseModel):
    """A single OCR token with text, position, and confidence.

    The ``text`` value is **immutable evidence** per AGENTS.md. Stages must not
    mutate it; normalization happens on copies during comparison only.
    """

    model_config = ConfigDict(frozen=True)

    text: str
    bbox: BoundingBox
    confidence: float = Field(ge=0.0, le=1.0)
