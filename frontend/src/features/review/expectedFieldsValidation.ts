import type { ExpectedFields } from "@/lib/types/api";

/**
 * Returns true when the form has the minimum data the backend needs.
 * Required: brand_name AND alcohol_content. Other fields are optional.
 */
export function expectedFieldsAreReady(v: ExpectedFields): boolean {
  return Boolean(
    v.brand_name &&
      v.brand_name.trim() &&
      v.alcohol_content &&
      v.alcohol_content.trim(),
  );
}
