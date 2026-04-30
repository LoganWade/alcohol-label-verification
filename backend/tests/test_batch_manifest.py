"""Tests for the manifest CSV parser.

The parser is the gatekeeper for batch submissions — every error must
surface as structured data, never an exception. These tests cover the
file-level errors (encoding, missing header, missing columns), the
per-row coercion (boolean, attribution enum, required fields), and the
cross-row invariants (one primary, agreeing fields, unique filenames).
"""

from __future__ import annotations

import pytest

from app.core.constants import ImageAttribution
from app.services.batch.manifest import parse_manifest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _csv(*rows: str) -> bytes:
    return ("\n".join(rows) + "\n").encode("utf-8")


HEADER = (
    "serial_number,brand_name,fanciful_name,class_type,alcohol_content,"
    "net_contents,bottler,country_of_origin,image_filename,attribution,"
    "is_primary"
)
MIN_HEADER = "serial_number,image_filename,attribution,is_primary"


# ---------------------------------------------------------------------------
# File-level errors
# ---------------------------------------------------------------------------
def test_empty_manifest_returns_structured_error() -> None:
    result = parse_manifest(b"", max_applications=10)
    assert not result.ok
    assert len(result.errors) == 1
    assert result.errors[0].code == "manifest_empty"
    assert result.errors[0].row_number == 0


def test_non_utf8_manifest_is_rejected_cleanly() -> None:
    # 0xFF is invalid as a UTF-8 start byte.
    result = parse_manifest(b"\xff\xfeserial_number\n", max_applications=10)
    assert not result.ok
    assert result.errors[0].code == "manifest_not_utf8"


def test_header_with_no_data_rows_errors() -> None:
    result = parse_manifest(_csv(MIN_HEADER), max_applications=10)
    assert not result.ok
    assert any(e.code == "manifest_no_rows" for e in result.errors)


def test_excel_bom_is_tolerated() -> None:
    csv_bytes = "\ufeff" + MIN_HEADER + "\nA1,a.png,front,true\n"
    result = parse_manifest(csv_bytes.encode("utf-8"), max_applications=10)
    assert result.ok, result.errors


def test_missing_required_column_lists_all_missing() -> None:
    # Drop image_filename and is_primary
    bad = _csv("serial_number,attribution", "A1,front")
    result = parse_manifest(bad, max_applications=10)
    assert not result.ok
    err = next(e for e in result.errors if e.code == "manifest_missing_columns")
    assert "image_filename" in err.message
    assert "is_primary" in err.message


def test_unknown_column_is_rejected() -> None:
    bad = _csv(
        MIN_HEADER + ",mystery_field",
        "A1,a.png,front,true,oops",
    )
    result = parse_manifest(bad, max_applications=10)
    assert not result.ok
    assert any(e.code == "manifest_unknown_columns" for e in result.errors)


# ---------------------------------------------------------------------------
# Per-row coercion
# ---------------------------------------------------------------------------
def test_happy_path_one_application_one_image() -> None:
    csv_bytes = _csv(MIN_HEADER, "A1,a.png,front,true")
    result = parse_manifest(csv_bytes, max_applications=10)
    assert result.ok, result.errors
    assert len(result.applications) == 1
    app = result.applications[0]
    assert app.fields.serial_number == "A1"
    assert app.image_filenames == ("a.png",)
    assert app.primary_image_filename == "a.png"
    assert app.attributions_by_filename["a.png"] == ImageAttribution.FRONT


def test_multi_image_application_groups_by_serial() -> None:
    csv_bytes = _csv(
        HEADER,
        "A1,Brand X,,Vodka,40%,750 mL,Acme,USA,front.png,front,true",
        "A1,Brand X,,Vodka,40%,750 mL,Acme,USA,back.png,back,false",
        "A1,Brand X,,Vodka,40%,750 mL,Acme,USA,neck.png,neck,false",
    )
    result = parse_manifest(csv_bytes, max_applications=10)
    assert result.ok, result.errors
    assert len(result.applications) == 1
    app = result.applications[0]
    assert app.image_filenames == ("front.png", "back.png", "neck.png")
    assert app.primary_image_filename == "front.png"
    assert app.fields.brand_name == "Brand X"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("true", True),
        ("True", True),
        ("1", True),
        ("yes", True),
        ("Y", True),
        ("false", False),
        ("0", False),
        ("no", False),
        ("", False),
    ],
)
def test_is_primary_boolean_aliases(raw: str, expected: bool) -> None:
    csv_bytes = _csv(MIN_HEADER, f"A1,a.png,front,{raw}")
    result = parse_manifest(csv_bytes, max_applications=10)
    if expected:
        assert result.ok, result.errors
    else:
        # is_primary=false on the only image means no primary => error
        assert not result.ok
        assert any(e.code == "no_primary_image" for e in result.errors)


def test_invalid_is_primary_value_is_reported() -> None:
    csv_bytes = _csv(MIN_HEADER, "A1,a.png,front,maybe")
    result = parse_manifest(csv_bytes, max_applications=10)
    assert not result.ok
    err = next(e for e in result.errors if e.code == "row_invalid_is_primary")
    assert err.column == "is_primary"
    assert err.row_number == 1


def test_invalid_attribution_is_reported() -> None:
    csv_bytes = _csv(MIN_HEADER, "A1,a.png,trunk,true")
    result = parse_manifest(csv_bytes, max_applications=10)
    assert not result.ok
    err = next(e for e in result.errors if e.code == "row_invalid_attribution")
    assert "trunk" in err.message


def test_missing_serial_or_filename_is_reported() -> None:
    csv_bytes = _csv(
        MIN_HEADER,
        ",a.png,front,true",
        "A1,,front,true",
    )
    result = parse_manifest(csv_bytes, max_applications=10)
    assert not result.ok
    codes = {e.code for e in result.errors}
    assert "row_missing_serial" in codes
    assert "row_missing_image" in codes


# ---------------------------------------------------------------------------
# Cross-row validation
# ---------------------------------------------------------------------------
def test_field_disagreement_between_rows_for_same_serial_is_reported() -> None:
    csv_bytes = _csv(
        HEADER,
        "A1,Brand X,,Vodka,40%,750 mL,Acme,USA,front.png,front,true",
        "A1,Brand Y,,Vodka,40%,750 mL,Acme,USA,back.png,back,false",
    )
    result = parse_manifest(csv_bytes, max_applications=10)
    assert not result.ok
    err = next(e for e in result.errors if e.code == "row_field_disagreement")
    assert err.column == "brand_name"


def test_no_primary_image_is_reported() -> None:
    csv_bytes = _csv(
        MIN_HEADER,
        "A1,a.png,front,false",
        "A1,b.png,back,false",
    )
    result = parse_manifest(csv_bytes, max_applications=10)
    assert not result.ok
    assert any(e.code == "no_primary_image" for e in result.errors)


def test_multiple_primary_images_is_reported() -> None:
    csv_bytes = _csv(
        MIN_HEADER,
        "A1,a.png,front,true",
        "A1,b.png,back,true",
    )
    result = parse_manifest(csv_bytes, max_applications=10)
    assert not result.ok
    assert any(e.code == "multiple_primary_images" for e in result.errors)


def test_duplicate_image_filename_within_application_is_reported() -> None:
    csv_bytes = _csv(
        MIN_HEADER,
        "A1,a.png,front,true",
        "A1,a.png,back,false",
    )
    result = parse_manifest(csv_bytes, max_applications=10)
    assert not result.ok
    assert any(e.code == "duplicate_image_filename" for e in result.errors)


def test_too_many_applications_is_reported_at_file_level() -> None:
    rows = [MIN_HEADER]
    for i in range(5):
        rows.append(f"A{i},img{i}.png,front,true")
    csv_bytes = _csv(*rows)
    result = parse_manifest(csv_bytes, max_applications=3)
    assert not result.ok
    err = next(e for e in result.errors if e.code == "too_many_applications")
    assert "5" in err.message
    assert "3" in err.message


def test_two_applications_preserve_manifest_order() -> None:
    csv_bytes = _csv(
        MIN_HEADER,
        "B1,b.png,front,true",
        "A1,a.png,front,true",
    )
    result = parse_manifest(csv_bytes, max_applications=10)
    assert result.ok, result.errors
    assert [a.fields.serial_number for a in result.applications] == ["B1", "A1"]
