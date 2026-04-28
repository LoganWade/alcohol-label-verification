import type { ExpectedFields } from "@/lib/types/api";

/**
 * Phase 2 stub-aligned sample; replace with seeded fixture set in Phase 3.
 *
 * These expected values match the Phase 1 stub OCR output for the
 * "Old Tom Distillery" demo label so that the reviewer can:
 *   1. Click "Load sample" on the Expected fields form
 *   2. Upload any image (the stub backend returns canned data regardless)
 *   3. See a meaningful end-to-end result against the stub backend
 *
 * When Phase 3 introduces seeded labels and a real OCR provider, swap this
 * for the seeded fixture set under sample_data/expected_fields/.
 */
export const STUB_SAMPLE_EXPECTED_FIELDS: ExpectedFields = {
  brand_name: "Old Tom Distillery",
  class_type: "Kentucky Straight Bourbon Whiskey",
  alcohol_content: "45% Alc./Vol.",
  net_contents: "750 mL",
  bottler: "Bottled by Old Tom Co., Frankfort, KY",
  country_of_origin: null,
  warning: null,
};

/** TTB statutory text (27 CFR 16.21). Mirrors backend constants. */
export const DEFAULT_GOVERNMENT_WARNING =
  "GOVERNMENT WARNING: (1) According to the Surgeon General, women should " +
  "not drink alcoholic beverages during pregnancy because of the risk of " +
  "birth defects. (2) Consumption of alcoholic beverages impairs your " +
  "ability to drive a car or operate machinery, and may cause health " +
  "problems.";
