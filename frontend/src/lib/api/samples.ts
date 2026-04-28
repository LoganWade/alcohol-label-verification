/**
 * Samples API client — read-only access to demo label fixtures.
 *
 * Three calls mirror the three backend endpoints in samples.py:
 *   listSamples()             → GET /api/v1/samples
 *   getSampleImageUrl(id)     → builds the image URL (used as <img src>)
 *   getSampleExpectedFields() → GET /api/v1/samples/{id}/expected-fields
 *
 * Error handling follows the same AnalyzeApiError pattern as client.ts so
 * callers can use a single error boundary.
 */

import type { ExpectedFields, SampleSummary } from "@/lib/types/api";
import { API_BASE_URL, AnalyzeApiError } from "@/lib/api/client";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function _handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let envelope;
    try {
      const body = await res.json();
      const detail = body?.detail ?? body;
      envelope = {
        code: detail?.code ?? `http_${res.status}`,
        message:
          detail?.message ?? `Server returned ${res.status} ${res.statusText}.`,
        recovery_hint: detail?.recovery_hint ?? null,
      };
    } catch {
      envelope = {
        code: `http_${res.status}`,
        message: `Server returned ${res.status} ${res.statusText}.`,
        recovery_hint: "Try again in a moment.",
      };
    }
    throw new AnalyzeApiError(envelope, res.status);
  }
  return (await res.json()) as T;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/** Fetch the full list of available demo samples. */
export async function listSamples(): Promise<SampleSummary[]> {
  const res = await fetch(`${API_BASE_URL}/samples`);
  return _handleResponse<SampleSummary[]>(res);
}

/**
 * Return the URL for a sample's label image.
 * Used directly as `<img src={getSampleImageUrl(id)} />` so the browser
 * streams the PNG without an intermediate Blob URL.
 */
export function getSampleImageUrl(sampleId: string): string {
  return `${API_BASE_URL}/samples/${encodeURIComponent(sampleId)}/image`;
}

/** Fetch the pre-filled ExpectedFields for a demo sample. */
export async function getSampleExpectedFields(
  sampleId: string,
): Promise<ExpectedFields> {
  const res = await fetch(
    `${API_BASE_URL}/samples/${encodeURIComponent(sampleId)}/expected-fields`,
  );
  return _handleResponse<ExpectedFields>(res);
}
