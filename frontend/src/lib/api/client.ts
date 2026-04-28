/**
 * Thin API client. One call: POST /reviews/analyze.
 *
 * - Uses fetch with AbortController so the processing screen's Cancel button
 *   actually stops the request.
 * - Parses the structured AnalyzeError envelope on non-2xx responses so the
 *   UI can render the message + recovery_hint verbatim.
 */

import type { AnalyzeError, AnalyzeResponse, ExpectedFields } from "@/lib/types/api";

const DEFAULT_BASE = "http://localhost:8000/api/v1";

export const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? DEFAULT_BASE;

export class AnalyzeApiError extends Error {
  readonly envelope: AnalyzeError;
  readonly httpStatus: number | null;

  constructor(envelope: AnalyzeError, httpStatus: number | null) {
    super(envelope.message);
    this.envelope = envelope;
    this.httpStatus = httpStatus;
    this.name = "AnalyzeApiError";
  }
}

interface AnalyzeArgs {
  image: File;
  expectedFields: ExpectedFields;
  signal?: AbortSignal;
}

export async function analyzeLabel({
  image,
  expectedFields,
  signal,
}: AnalyzeArgs): Promise<AnalyzeResponse> {
  const form = new FormData();
  form.append("image", image);
  form.append("expected_fields", JSON.stringify(expectedFields));

  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/reviews/analyze`, {
      method: "POST",
      body: form,
      signal,
    });
  } catch (err) {
    // AbortError is re-thrown so callers can distinguish user cancel.
    if ((err as Error)?.name === "AbortError") throw err;
    throw new AnalyzeApiError(
      {
        code: "network_error",
        message: "Could not reach the review service.",
        recovery_hint:
          "Check your connection and try again. If the problem continues, contact support.",
      },
      null,
    );
  }

  if (!res.ok) {
    let envelope: AnalyzeError;
    try {
      const body = await res.json();
      // FastAPI wraps custom error payloads under `detail`.
      const detail = body?.detail ?? body;
      envelope = {
        code: detail?.code ?? `http_${res.status}`,
        message:
          detail?.message ??
          `Server returned ${res.status} ${res.statusText}.`,
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

  return (await res.json()) as AnalyzeResponse;
}
