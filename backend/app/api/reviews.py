"""Reviews API: the analyze endpoint."""

from __future__ import annotations

import json

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from pydantic import ValidationError

from app.core.settings import settings
from app.schemas.fields import ExpectedFields
from app.schemas.review import AnalyzeError, AnalyzeResponse
from app.services.pipeline import analyze

router = APIRouter(prefix="/reviews", tags=["reviews"])


def _error(code: str, message: str, recovery: str | None = None) -> AnalyzeError:
    return AnalyzeError(code=code, message=message, recovery_hint=recovery)


@router.post(
    "/analyze",
    response_model=AnalyzeResponse,
    responses={
        400: {"model": AnalyzeError},
        413: {"model": AnalyzeError},
        415: {"model": AnalyzeError},
    },
)
async def analyze_label(
    image: UploadFile = File(..., description="Label image (PNG/JPG) or single-page PDF."),
    expected_fields: str = Form(
        ...,
        description="JSON-encoded ExpectedFields. Use null for fields not supplied.",
    ),
) -> AnalyzeResponse:
    """Run the full extraction + validation pipeline on one label.

    The endpoint accepts multipart/form-data with two parts:

    - ``image``: the label file
    - ``expected_fields``: a JSON string matching the ExpectedFields schema

    Errors are returned as a structured ``AnalyzeError`` envelope so the
    frontend can render plain-language recovery hints (AGENTS.md UX rules).
    """

    # --- Validate content type --------------------------------------------
    if image.content_type not in settings.allowed_image_types:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=_error(
                code="unsupported_media_type",
                message=(
                    f"File type {image.content_type!r} is not supported. "
                    f"Please upload a PNG, JPEG, or single-page PDF."
                ),
                recovery="Convert the file to PNG or JPEG and try again.",
            ).model_dump(),
        )

    # --- Read + size guard ------------------------------------------------
    body = await image.read()
    if len(body) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=_error(
                code="file_too_large",
                message=(
                    f"This file is {len(body) // (1024 * 1024)} MB. "
                    f"Please upload an image under "
                    f"{settings.max_upload_bytes // (1024 * 1024)} MB."
                ),
                recovery="Resize the image to a smaller resolution and try again.",
            ).model_dump(),
        )

    if not body:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_error(
                code="empty_file",
                message="The uploaded file is empty.",
                recovery="Choose a different file and try again.",
            ).model_dump(),
        )

    # --- Parse expected_fields -------------------------------------------
    try:
        expected_payload = json.loads(expected_fields) if expected_fields else {}
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_error(
                code="invalid_expected_fields_json",
                message=f"expected_fields is not valid JSON: {exc.msg}.",
                recovery="Check the JSON syntax and try again.",
            ).model_dump(),
        ) from exc

    try:
        expected = ExpectedFields.model_validate(expected_payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_error(
                code="invalid_expected_fields_schema",
                message="expected_fields does not match the required shape.",
                recovery=str(exc.errors()[:3]),
            ).model_dump(),
        ) from exc

    # --- Run pipeline ----------------------------------------------------
    try:
        return analyze(image_bytes=body, expected=expected)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_error(
                code="unreadable_image",
                message=(
                    "The image could not be read. "
                    "It may be corrupt or in an unsupported format."
                ),
                recovery="Try re-saving the image as PNG or JPEG and upload again.",
            ).model_dump(),
        ) from exc
