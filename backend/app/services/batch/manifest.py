"""CSV manifest parser for batch submissions.

The manifest is the source of truth for which applications a batch
contains, what their importer-stated COLA fields are, and how many
images each one has. The parser converts a raw CSV byte string into
either a list of validated ``ManifestRow`` records grouped by
``serial_number`` or a list of structured errors the importer can act on.

Why a custom parser instead of pandas
-------------------------------------
We accept arbitrary user-uploaded CSV. pandas would silently coerce
"01" to int 1, drop leading zeros from serial numbers, and infer dtypes
we don't want. ``csv.DictReader`` keeps every cell a string and lets us
attach error messages with row + column granularity.

Errors as data
--------------
Every validation failure becomes a ``ManifestError`` with
``row_number`` (1-based, header row excluded), ``column``, ``code``,
and ``message``. The API returns the full list — never the first error
only — because importers expect to fix everything in one pass.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from typing import Final

from pydantic import ValidationError

from app.core.constants import ImageAttribution
from app.schemas.batch import ApplicationFields

# ---------------------------------------------------------------------------
# Public schema (column names + truthy/falsey forms)
# ---------------------------------------------------------------------------
REQUIRED_COLUMNS: Final[tuple[str, ...]] = (
    "serial_number",
    "image_filename",
    "attribution",
    "is_primary",
)

OPTIONAL_COLUMNS: Final[tuple[str, ...]] = (
    "brand_name",
    "fanciful_name",
    "class_type",
    "alcohol_content",
    "net_contents",
    "bottler",
    "country_of_origin",
)

ALL_COLUMNS: Final[frozenset[str]] = frozenset(REQUIRED_COLUMNS + OPTIONAL_COLUMNS)

_TRUE = frozenset({"1", "true", "yes", "y", "t"})
_FALSE = frozenset({"0", "false", "no", "n", "f", ""})

# Importer-stated COLA field columns the manifest may carry.
_FIELD_COLUMNS: Final[tuple[str, ...]] = OPTIONAL_COLUMNS


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class ManifestRow:
    """One row of the manifest after type coercion. One per (app, image)."""

    row_number: int  # 1-based, excluding header
    serial_number: str
    image_filename: str
    attribution: ImageAttribution
    is_primary: bool
    fields: dict[str, str | None]  # subset of ApplicationFields kwargs


@dataclass(frozen=True, slots=True)
class ManifestError:
    """One validation failure. Importers fix all of them in one pass."""

    row_number: int  # 0 for file-level errors (missing columns, empty CSV)
    column: str | None
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class ManifestApplication:
    """One application's worth of grouped rows after parsing succeeds.

    The parser groups rows by ``serial_number`` and resolves which image
    is the primary one. Downstream consumers read this structure
    directly; the raw rows are not exposed.
    """

    fields: ApplicationFields
    image_filenames: tuple[str, ...]
    primary_image_filename: str
    attributions_by_filename: dict[str, ImageAttribution]


@dataclass(frozen=True, slots=True)
class ManifestParseResult:
    """Successful parse: applications in manifest order, no errors."""

    applications: tuple[ManifestApplication, ...]
    errors: tuple[ManifestError, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return not self.errors


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------
def parse_manifest(
    csv_bytes: bytes,
    *,
    max_applications: int,
) -> ManifestParseResult:
    """Parse the manifest. Always returns a result — never raises.

    A ``ManifestParseResult`` with non-empty ``errors`` and empty
    ``applications`` indicates a failed parse. Partial success is not
    supported: any error means the whole submission is rejected, so we
    do not return a partial application list.

    ``max_applications`` is enforced server-side here so the API can
    surface "too many applications" as a manifest-level error rather
    than a 400 response.
    """

    errors: list[ManifestError] = []

    # --- decode + sniff ----------------------------------------------------
    try:
        text = csv_bytes.decode("utf-8-sig")  # tolerate Excel BOM
    except UnicodeDecodeError:
        return ManifestParseResult(
            applications=(),
            errors=(
                ManifestError(
                    row_number=0,
                    column=None,
                    code="manifest_not_utf8",
                    message="Manifest must be a UTF-8 encoded CSV file.",
                ),
            ),
        )

    if not text.strip():
        return ManifestParseResult(
            applications=(),
            errors=(
                ManifestError(
                    row_number=0,
                    column=None,
                    code="manifest_empty",
                    message="Manifest is empty.",
                ),
            ),
        )

    reader = csv.DictReader(io.StringIO(text))
    fieldnames = [h.strip() for h in (reader.fieldnames or [])]
    if not fieldnames:
        return ManifestParseResult(
            applications=(),
            errors=(
                ManifestError(
                    row_number=0,
                    column=None,
                    code="manifest_no_header",
                    message="Manifest has no header row.",
                ),
            ),
        )

    # --- header validation ------------------------------------------------
    missing = [c for c in REQUIRED_COLUMNS if c not in fieldnames]
    if missing:
        errors.append(
            ManifestError(
                row_number=0,
                column=",".join(missing),
                code="manifest_missing_columns",
                message=(
                    "Manifest is missing required columns: "
                    f"{', '.join(missing)}."
                ),
            )
        )
    unknown = [c for c in fieldnames if c not in ALL_COLUMNS]
    if unknown:
        errors.append(
            ManifestError(
                row_number=0,
                column=",".join(unknown),
                code="manifest_unknown_columns",
                message=(
                    "Manifest has unrecognized columns: "
                    f"{', '.join(unknown)}. Remove them and try again."
                ),
            )
        )
    if errors:
        # Don't bother row-validating if the schema is wrong — every row
        # would produce confusing follow-on errors.
        return ManifestParseResult(applications=(), errors=tuple(errors))

    # --- row-by-row coercion ----------------------------------------------
    rows: list[ManifestRow] = []
    for i, raw_row in enumerate(reader, start=1):  # i = data row #
        row_errors, row = _coerce_row(i, raw_row)
        errors.extend(row_errors)
        if row is not None:
            rows.append(row)

    if not rows and not errors:
        errors.append(
            ManifestError(
                row_number=0,
                column=None,
                code="manifest_no_rows",
                message="Manifest has a header but no data rows.",
            )
        )

    if errors:
        return ManifestParseResult(applications=(), errors=tuple(errors))

    # --- group by serial_number, run cross-row checks ---------------------
    apps, group_errors = _group_rows(rows, max_applications=max_applications)
    if group_errors:
        return ManifestParseResult(applications=(), errors=tuple(group_errors))

    return ManifestParseResult(applications=apps, errors=())


# ---------------------------------------------------------------------------
# Per-row coercion
# ---------------------------------------------------------------------------
def _coerce_row(
    row_number: int, raw: dict[str, str | None]
) -> tuple[list[ManifestError], ManifestRow | None]:
    """Validate one CSV row. Returns (errors, parsed-or-None)."""

    errs: list[ManifestError] = []

    def _strip(value: str | None) -> str:
        return (value or "").strip()

    serial = _strip(raw.get("serial_number"))
    if not serial:
        errs.append(
            ManifestError(
                row_number=row_number,
                column="serial_number",
                code="row_missing_serial",
                message="serial_number is required on every row.",
            )
        )

    image_filename = _strip(raw.get("image_filename"))
    if not image_filename:
        errs.append(
            ManifestError(
                row_number=row_number,
                column="image_filename",
                code="row_missing_image",
                message="image_filename is required on every row.",
            )
        )

    attribution_raw = _strip(raw.get("attribution")).lower()
    attribution: ImageAttribution
    if not attribution_raw:
        # Default to FRONT only if is_primary is true; otherwise OTHER.
        attribution = ImageAttribution.OTHER  # caller may override
    else:
        try:
            attribution = ImageAttribution(attribution_raw)
        except ValueError:
            errs.append(
                ManifestError(
                    row_number=row_number,
                    column="attribution",
                    code="row_invalid_attribution",
                    message=(
                        f"attribution {attribution_raw!r} is not one of: "
                        f"{', '.join(a.value for a in ImageAttribution)}."
                    ),
                )
            )
            attribution = ImageAttribution.OTHER

    is_primary_raw = _strip(raw.get("is_primary")).lower()
    is_primary: bool
    if is_primary_raw in _TRUE:
        is_primary = True
    elif is_primary_raw in _FALSE:
        is_primary = False
    else:
        errs.append(
            ManifestError(
                row_number=row_number,
                column="is_primary",
                code="row_invalid_is_primary",
                message=(
                    f"is_primary {is_primary_raw!r} is not a boolean value. "
                    f"Use 'true'/'false' or '1'/'0'."
                ),
            )
        )
        is_primary = False

    fields: dict[str, str | None] = {}
    for col in _FIELD_COLUMNS:
        value = _strip(raw.get(col))
        fields[col] = value or None

    if errs:
        return errs, None

    return [], ManifestRow(
        row_number=row_number,
        serial_number=serial,
        image_filename=image_filename,
        attribution=attribution,
        is_primary=is_primary,
        fields=fields,
    )


# ---------------------------------------------------------------------------
# Grouping + cross-row validation
# ---------------------------------------------------------------------------
def _group_rows(
    rows: list[ManifestRow],
    *,
    max_applications: int,
) -> tuple[tuple[ManifestApplication, ...], list[ManifestError]]:
    """Group rows by serial_number; enforce per-application invariants.

    Invariants checked:
    - All rows for one serial_number must have identical importer-stated
      COLA fields. (A typo in row 5 versus row 6 should be flagged loud,
      not silently merged.)
    - Each application has exactly one ``is_primary == True`` row.
    - Image filenames within one application are unique.
    - ``len(applications) <= max_applications``.
    """

    errors: list[ManifestError] = []

    # Preserve manifest order: first appearance of each serial wins.
    order: list[str] = []
    grouped: dict[str, list[ManifestRow]] = {}
    for row in rows:
        if row.serial_number not in grouped:
            order.append(row.serial_number)
            grouped[row.serial_number] = []
        grouped[row.serial_number].append(row)

    if len(order) > max_applications:
        errors.append(
            ManifestError(
                row_number=0,
                column="serial_number",
                code="too_many_applications",
                message=(
                    f"Manifest has {len(order)} applications, but the "
                    f"per-batch limit is {max_applications}. Split this "
                    f"submission into smaller batches."
                ),
            )
        )

    apps: list[ManifestApplication] = []
    for serial in order:
        group = grouped[serial]
        first = group[0]

        # 1. fields agreement
        for row in group[1:]:
            for col, val in row.fields.items():
                if first.fields[col] != val:
                    errors.append(
                        ManifestError(
                            row_number=row.row_number,
                            column=col,
                            code="row_field_disagreement",
                            message=(
                                f"{col} differs from row {first.row_number} "
                                f"for serial_number {serial!r}: "
                                f"{first.fields[col]!r} vs {val!r}. "
                                f"All rows for one application must agree."
                            ),
                        )
                    )

        # 2. exactly one primary
        primaries = [r for r in group if r.is_primary]
        if len(primaries) == 0:
            errors.append(
                ManifestError(
                    row_number=first.row_number,
                    column="is_primary",
                    code="no_primary_image",
                    message=(
                        f"Application {serial!r} has no primary image. "
                        f"Mark exactly one row with is_primary=true."
                    ),
                )
            )
        elif len(primaries) > 1:
            for r in primaries[1:]:
                errors.append(
                    ManifestError(
                        row_number=r.row_number,
                        column="is_primary",
                        code="multiple_primary_images",
                        message=(
                            f"Application {serial!r} has multiple "
                            f"is_primary=true rows. Choose exactly one."
                        ),
                    )
                )

        # 3. unique filenames within an application
        seen: dict[str, int] = {}
        for r in group:
            if r.image_filename in seen:
                errors.append(
                    ManifestError(
                        row_number=r.row_number,
                        column="image_filename",
                        code="duplicate_image_filename",
                        message=(
                            f"image_filename {r.image_filename!r} appears "
                            f"twice for application {serial!r} (also row "
                            f"{seen[r.image_filename]})."
                        ),
                    )
                )
            else:
                seen[r.image_filename] = r.row_number

        # 4. assemble app (only if no errors specific to this group; we
        #    still build one to keep ordering stable, but downstream
        #    callers must check ``errors`` first).
        if primaries:
            primary_filename = primaries[0].image_filename
        else:
            primary_filename = first.image_filename
        try:
            app_fields = ApplicationFields(serial_number=serial, **first.fields)
        except ValidationError as exc:
            for err in exc.errors():
                col = ".".join(str(p) for p in err.get("loc", ())) or "fields"
                errors.append(
                    ManifestError(
                        row_number=first.row_number,
                        column=col,
                        code="row_invalid_field",
                        message=err.get("msg", "Invalid field value."),
                    )
                )
            continue

        attributions = {r.image_filename: r.attribution for r in group}
        apps.append(
            ManifestApplication(
                fields=app_fields,
                image_filenames=tuple(r.image_filename for r in group),
                primary_image_filename=primary_filename,
                attributions_by_filename=attributions,
            )
        )

    return tuple(apps), errors


__all__ = [
    "ALL_COLUMNS",
    "OPTIONAL_COLUMNS",
    "REQUIRED_COLUMNS",
    "ManifestApplication",
    "ManifestError",
    "ManifestParseResult",
    "ManifestRow",
    "parse_manifest",
]
