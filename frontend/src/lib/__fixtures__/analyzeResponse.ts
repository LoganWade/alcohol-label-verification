import type {
  AnalyzeResponse,
  ExtractedField,
  FieldComparison,
  FieldName,
} from "@/lib/types/api";

function ef(field: FieldName, raw: string | null): ExtractedField {
  return {
    field,
    raw_text: raw,
    normalized_text: raw ? raw.toLowerCase() : null,
    evidence_bbox: { x0: 10, y0: 20, x1: 100, y1: 60 },
    confidence: "high",
    notes: null,
  };
}

function comp(
  field: FieldName,
  status: FieldComparison["status"],
  expected: string | null,
  found: string | null,
  reason: string,
  confidence: FieldComparison["confidence"] = "high",
  bbox: FieldComparison["evidence_bbox"] = { x0: 10, y0: 20, x1: 100, y1: 60 },
): FieldComparison {
  return {
    field,
    expected,
    found_raw: found,
    found_normalized: found ? found.toLowerCase() : null,
    status,
    reason,
    confidence,
    evidence_bbox: bbox,
  };
}

/** Fixture covering all five field statuses + a Mismatch warning row. */
export const FULL_FIXTURE: AnalyzeResponse = {
  review_id: "rev_test_001",
  summary: {
    status: "Needs Review",
    headline:
      "5 of 6 fields match. 1 needs review and the Government Warning has a header issue.",
  },
  extracted_fields: {
    brand_name: ef("brand_name", "OLD TOM DISTILLERY"),
    class_type: ef("class_type", "Kentucky Straight Bourbon Whiskey"),
    alcohol_content: ef("alcohol_content", "45% Alc./Vol."),
    net_contents: ef("net_contents", "750 ML"),
    bottler: ef("bottler", "Old Tom Co., Frankfurt KY"),
    country_of_origin: { ...ef("country_of_origin", null), confidence: "uncertain" },
    warning: ef("warning", "Government Warning: ..."),
  },
  field_comparisons: [
    comp(
      "brand_name",
      "Match",
      "Old Tom Distillery",
      "OLD TOM DISTILLERY",
      "Case-only difference; normalized exact match.",
    ),
    comp(
      "class_type",
      "Match",
      "Kentucky Straight Bourbon Whiskey",
      "Kentucky Straight Bourbon Whiskey",
      "Exact match.",
    ),
    comp(
      "alcohol_content",
      "Match",
      "45% Alc./Vol.",
      "45% Alc./Vol.",
      "Exact match.",
    ),
    comp(
      "net_contents",
      "Match",
      "750 mL",
      "750 ML",
      "Case-only difference.",
    ),
    comp(
      "bottler",
      "Needs Review",
      "Bottled by Old Tom Co., Frankfort, KY",
      "Old Tom Co., Frankfurt KY",
      "Possible OCR confusion of city name.",
      "medium",
    ),
    comp(
      "country_of_origin",
      "Missing",
      null,
      null,
      "No expected value supplied; nothing to compare.",
      "uncertain",
      null,
    ),
  ],
  warning_validation: {
    status: "Mismatch",
    header_caps_ok: false,
    wording_match: true,
    raw_text: "Government Warning: (1) According to ...",
    expected_text: "GOVERNMENT WARNING: ...",
    reason: "Header 'Government Warning' is not in all caps.",
    evidence_bbox: { x0: 80, y0: 1120, x1: 720, y1: 1280 },
  },
  processing: {
    elapsed_ms: 3420,
    image_quality: "good",
    stages_ms: {
      preprocess_ms: 280,
      ocr_ms: 2640,
      region_attribution_ms: 50,
      field_extraction_ms: 60,
      comparison_ms: 90,
      warning_validation_ms: 200,
      reporting_ms: 100,
    },
    ocr_provider: "stub",
    version: "0.1.0",
  },
  limitations: [
    "This tool assists review and does not replace reviewer judgment.",
    "Stub OCR output; results are illustrative only.",
  ],
};

/** Build a response with a single field's comparison overridden. */
export function withFieldComparison(
  fieldName: FieldName,
  override: Partial<FieldComparison>,
): AnalyzeResponse {
  return {
    ...FULL_FIXTURE,
    field_comparisons: FULL_FIXTURE.field_comparisons.map((c) =>
      c.field === fieldName ? { ...c, ...override } : c,
    ),
  };
}

/** Build a response with a different warning validation. */
export function withWarning(
  override: Partial<AnalyzeResponse["warning_validation"]>,
): AnalyzeResponse {
  return {
    ...FULL_FIXTURE,
    warning_validation: { ...FULL_FIXTURE.warning_validation, ...override },
  };
}

/**
 * Fixture with one of every field status — used by results-screen tests that
 * verify all five chips render simultaneously.
 */
export const ALL_STATUSES_FIXTURE: AnalyzeResponse = {
  ...FULL_FIXTURE,
  field_comparisons: [
    comp("brand_name", "Match", "Old Tom Distillery", "Old Tom Distillery", "Exact match."),
    comp("class_type", "Mismatch", "Bourbon", "Vodka", "Different value."),
    comp("alcohol_content", "Missing", "45% Alc./Vol.", null, "Not detected on label.", "uncertain", null),
    comp("net_contents", "Needs Review", "750 mL", "75O mL", "OCR ambiguity (O vs 0).", "medium"),
    comp("bottler", "Uncertain", "Old Tom Co.", null, "Image quality too poor to extract.", "uncertain", null),
    comp("country_of_origin", "Match", null, null, "No expected; nothing to compare.", "uncertain", null),
  ],
};
