/**
 * API client for the batch upload endpoints.
 *
 * Mirrors the backend's URL space:
 *   POST   /batches                          create
 *   GET    /batches                          list with summary counts
 *   GET    /batches/{id}                     detail with applications
 *   GET    /applications/{id}                one application
 *   PUT    /applications/{id}/decision       set workflow status
 *   POST   /batches/{id}/bulk-approve        approve all clean matches
 *
 * Errors come back as the same AnalyzeError envelope used by the
 * single-image flow, so the frontend renders one error shape across both
 * surfaces. The 400 from POST /batches additionally carries
 * `manifest_errors: ManifestError[]` for per-row feedback.
 */

import { API_BASE_URL } from "@/lib/api/client";
import type {
  AnalyzeError,
  Batch,
  BatchApplication,
  BatchDetail,
  BulkApproveResponse,
  ManifestError,
  WorkflowStatus,
} from "@/lib/types/api";

export class BatchApiError extends Error {
  readonly envelope: AnalyzeError;
  readonly httpStatus: number | null;
  readonly manifestErrors: ManifestError[];

  constructor(
    envelope: AnalyzeError,
    httpStatus: number | null,
    manifestErrors: ManifestError[] = [],
  ) {
    super(envelope.message);
    this.envelope = envelope;
    this.httpStatus = httpStatus;
    this.manifestErrors = manifestErrors;
    this.name = "BatchApiError";
  }
}

async function _throwIfError(res: Response): Promise<void> {
  if (res.ok) return;
  let envelope: AnalyzeError;
  let manifestErrors: ManifestError[] = [];
  try {
    const body = await res.json();
    const detail = body?.detail ?? body;
    envelope = {
      code: detail?.code ?? `http_${res.status}`,
      message:
        detail?.message ?? `Server returned ${res.status} ${res.statusText}.`,
      recovery_hint: detail?.recovery_hint ?? null,
    };
    if (Array.isArray(detail?.manifest_errors)) {
      manifestErrors = detail.manifest_errors as ManifestError[];
    }
  } catch {
    envelope = {
      code: `http_${res.status}`,
      message: `Server returned ${res.status} ${res.statusText}.`,
      recovery_hint: "Try again in a moment.",
    };
  }
  throw new BatchApiError(envelope, res.status, manifestErrors);
}

// ---------------------------------------------------------------------------
// Create
// ---------------------------------------------------------------------------
export interface CreateBatchArgs {
  meta: {
    importer_name: string;
    importer_email: string;
    note?: string | null;
  };
  manifestFile: File;
  imageFiles: File[];
  signal?: AbortSignal;
}

export async function createBatch({
  meta,
  manifestFile,
  imageFiles,
  signal,
}: CreateBatchArgs): Promise<Batch> {
  const form = new FormData();
  form.append("meta", JSON.stringify(meta));
  form.append("manifest", manifestFile);
  for (const f of imageFiles) {
    // Field name `images` (plural) — FastAPI binds this to a list.
    form.append("images", f);
  }
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/batches`, {
      method: "POST",
      body: form,
      signal,
    });
  } catch (err) {
    if ((err as Error)?.name === "AbortError") throw err;
    throw new BatchApiError(
      {
        code: "network_error",
        message: "Could not reach the batch service.",
        recovery_hint:
          "Check your connection and try again. If the problem continues, contact support.",
      },
      null,
    );
  }
  await _throwIfError(res);
  return (await res.json()) as Batch;
}

// ---------------------------------------------------------------------------
// Read
// ---------------------------------------------------------------------------
export async function listBatches(signal?: AbortSignal): Promise<Batch[]> {
  const res = await fetch(`${API_BASE_URL}/batches`, { signal });
  await _throwIfError(res);
  return (await res.json()) as Batch[];
}

export async function getBatch(
  batchId: string,
  signal?: AbortSignal,
): Promise<BatchDetail> {
  const res = await fetch(`${API_BASE_URL}/batches/${batchId}`, { signal });
  await _throwIfError(res);
  return (await res.json()) as BatchDetail;
}

export async function getApplication(
  applicationId: string,
  signal?: AbortSignal,
): Promise<BatchApplication> {
  const res = await fetch(`${API_BASE_URL}/applications/${applicationId}`, {
    signal,
  });
  await _throwIfError(res);
  return (await res.json()) as BatchApplication;
}

/**
 * Build the URL for an application's image. Used directly as `<img src=...>`
 * so the browser caches it; we do not fetch through this layer.
 */
export function getApplicationImageUrl(
  applicationId: string,
  imageId: string,
): string {
  return `${API_BASE_URL}/applications/${encodeURIComponent(
    applicationId,
  )}/images/${encodeURIComponent(imageId)}`;
}

// ---------------------------------------------------------------------------
// Mutate
// ---------------------------------------------------------------------------
export async function setApplicationDecision(
  applicationId: string,
  decision: { workflow_status: WorkflowStatus; note?: string | null },
): Promise<BatchApplication> {
  const res = await fetch(
    `${API_BASE_URL}/applications/${applicationId}/decision`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(decision),
    },
  );
  await _throwIfError(res);
  return (await res.json()) as BatchApplication;
}

export async function bulkApproveBatch(
  batchId: string,
): Promise<BulkApproveResponse> {
  const res = await fetch(`${API_BASE_URL}/batches/${batchId}/bulk-approve`, {
    method: "POST",
  });
  await _throwIfError(res);
  return (await res.json()) as BulkApproveResponse;
}
