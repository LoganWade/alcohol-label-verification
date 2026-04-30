/**
 * API contract types — mirror backend Pydantic schemas verbatim.
 *
 * Source of truth: backend/app/schemas/*.py + backend/app/core/constants.py.
 * Status vocabulary is fixed and used verbatim across UI and API per
 * AGENTS.md "Fixed status vocabulary" rule.
 */

// ---- Fixed status vocabulary -------------------------------------------

export type FieldStatus =
  | "Match"
  | "Mismatch"
  | "Missing"
  | "Needs Review"
  | "Uncertain";

export type ReviewStatus = "Pass" | "Mismatch" | "Needs Review";

export type Confidence = "high" | "medium" | "low" | "uncertain";

export type ImageQuality = "good" | "fair" | "poor" | "failed";

// Fixed field name set — order is the order the UI renders them.
export type FieldName =
  | "brand_name"
  | "class_type"
  | "alcohol_content"
  | "net_contents"
  | "bottler"
  | "country_of_origin"
  | "warning";

// Excludes "warning" because the government warning has its own dedicated
// renderer (WarningValidation) and is not part of the field-by-field grid.
// Typing this as Exclude<FieldName, "warning">[] makes that contract a
// compile-time invariant rather than a hidden assumption.
export const FIELD_DISPLAY_ORDER: Exclude<FieldName, "warning">[] = [
  "brand_name",
  "class_type",
  "alcohol_content",
  "net_contents",
  "bottler",
  "country_of_origin",
];

// Plain-language labels — no jargon, 18F plain-language guidelines.
export const FIELD_LABELS: Record<FieldName, string> = {
  brand_name: "Brand name",
  class_type: "Class / type",
  alcohol_content: "Alcohol content",
  net_contents: "Net contents",
  bottler: "Bottler / producer",
  country_of_origin: "Country of origin",
  warning: "Government warning",
};

// ---- Common primitives -------------------------------------------------

export interface BoundingBox {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

// ---- Request shape -----------------------------------------------------

export interface ExpectedFields {
  brand_name: string | null;
  class_type: string | null;
  alcohol_content: string | null;
  net_contents: string | null;
  bottler: string | null;
  country_of_origin: string | null;
  warning: string | null;
}

// ---- Response shape ----------------------------------------------------

export interface ExtractedField {
  field: FieldName;
  raw_text: string | null;
  normalized_text: string | null;
  evidence_bbox: BoundingBox | null;
  confidence: Confidence;
  notes: string | null;
}

export interface ExtractedFields {
  brand_name: ExtractedField;
  class_type: ExtractedField;
  alcohol_content: ExtractedField;
  net_contents: ExtractedField;
  bottler: ExtractedField;
  country_of_origin: ExtractedField;
  warning: ExtractedField;
}

export interface FieldComparison {
  field: FieldName;
  expected: string | null;
  found_raw: string | null;
  found_normalized: string | null;
  status: FieldStatus;
  reason: string;
  confidence: Confidence;
  evidence_bbox: BoundingBox | null;
}

export interface WarningValidation {
  status: FieldStatus;
  header_caps_ok: boolean;
  wording_match: boolean;
  raw_text: string | null;
  expected_text: string;
  reason: string;
  evidence_bbox: BoundingBox | null;
}

export interface ReviewSummary {
  status: ReviewStatus;
  headline: string;
}

export interface StageTimings {
  preprocess_ms: number;
  ocr_ms: number;
  region_attribution_ms: number;
  field_extraction_ms: number;
  comparison_ms: number;
  warning_validation_ms: number;
  reporting_ms: number;
}

export interface ProcessingMetadata {
  elapsed_ms: number;
  image_quality: ImageQuality;
  stages_ms: StageTimings;
  ocr_provider: string;
  version: string;
}

export interface AnalyzeResponse {
  review_id: string;
  summary: ReviewSummary;
  extracted_fields: ExtractedFields;
  field_comparisons: FieldComparison[];
  warning_validation: WarningValidation;
  processing: ProcessingMetadata;
  limitations: string[];
}

// Error envelope — frontend renders message + recovery_hint verbatim.
export interface AnalyzeError {
  code: string;
  message: string;
  recovery_hint: string | null;
}

// ---- Batch upload types ------------------------------------------------
//
// Mirrors backend/app/schemas/batch.py + the ApplicationProcessingStatus,
// WorkflowStatus, and ImageAttribution enums in core/constants.py.

export type ApplicationProcessingStatus =
  | "pending"
  | "processing"
  | "done"
  | "failed";

export type WorkflowStatus =
  | "pending_review"
  | "approved"
  | "rejected"
  | "needs_correction";

export type ImageAttribution = "front" | "back" | "neck" | "body" | "other";

export interface LabelImage {
  id: string;
  filename: string;
  attribution: ImageAttribution;
  is_primary: boolean;
  byte_size: number;
  content_type: string;
}

export interface ApplicationFields {
  serial_number: string;
  brand_name: string | null;
  fanciful_name: string | null;
  class_type: string | null;
  alcohol_content: string | null;
  net_contents: string | null;
  bottler: string | null;
  country_of_origin: string | null;
}

export interface BatchApplication {
  id: string;
  batch_id: string;
  fields: ApplicationFields;
  processing_status: ApplicationProcessingStatus;
  workflow_status: WorkflowStatus;
  images: LabelImage[];
  analyze: AnalyzeResponse | null;
  error: AnalyzeError | null;
  created_at: string;
  processed_at: string | null;
  decided_at: string | null;
  decided_note: string | null;
}

export interface BatchSummaryCounts {
  total: number;
  pending: number;
  processing: number;
  done: number;
  failed: number;
  approved: number;
  rejected: number;
  needs_correction: number;
}

export interface Batch {
  id: string;
  importer_name: string;
  importer_email: string;
  note: string | null;
  counts: BatchSummaryCounts;
  created_at: string;
}

export interface BatchDetail extends Batch {
  applications: BatchApplication[];
}

export interface BulkApproveResponse {
  approved_count: number;
  skipped_count: number;
  skipped_reasons: Record<string, number>;
}

// One row of /batches errors. Row 0 = file-level problem.
export interface ManifestError {
  row_number: number;
  column: string | null;
  code: string;
  message: string;
}

export const PROCESSING_STATUS_LABELS: Record<
  ApplicationProcessingStatus,
  string
> = {
  pending: "Queued",
  processing: "Processing",
  done: "Analyzed",
  failed: "Failed",
};

export const WORKFLOW_STATUS_LABELS: Record<WorkflowStatus, string> = {
  pending_review: "Pending review",
  approved: "Approved",
  rejected: "Rejected",
  needs_correction: "Needs correction",
};

// ---- Demo / sample types ------------------------------------------------

export type SampleProvenance = "synthetic" | "public_ttb_reference";

/** Lightweight sample descriptor returned by GET /api/v1/samples. */
export interface SampleSummary {
  id: string;
  title: string;
  description: string;
  expected_outcome: string;
  provenance: SampleProvenance;
}

/** Batch-upload demo descriptor returned by GET /api/v1/samples/batch. */
export interface BatchSampleSummary {
  id: string;
  title: string;
  description: string;
  expected_outcome: string;
  provenance: SampleProvenance;
  importer_name: string;
  importer_email: string;
  note: string | null;
  image_filenames: string[];
}
