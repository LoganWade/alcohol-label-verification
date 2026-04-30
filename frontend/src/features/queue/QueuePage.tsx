import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Clock, Inbox, RefreshCcw } from "lucide-react";

import { Button } from "@/components/Button";
import { ErrorPanel } from "@/components/ErrorPanel";
import { StatusChip } from "@/components/StatusChip";
import {
  BatchApiError,
  bulkApproveBatch,
  getBatch,
  listBatches,
} from "@/lib/api/batches";
import {
  PROCESSING_STATUS_LABELS,
  WORKFLOW_STATUS_LABELS,
} from "@/lib/types/api";
import type {
  ApplicationProcessingStatus,
  Batch,
  BatchApplication,
  WorkflowStatus,
} from "@/lib/types/api";

/**
 * Analyst queue.
 *
 * Layout: list of recent batches on the left, the selected batch's
 * applications on the right. Clean matches can be approved in bulk;
 * everything else routes to the per-application detail page.
 *
 * Polling: while a batch has applications still pending or processing
 * we refetch every 1.5s. Once the queue is fully analyzed the
 * polling stops to avoid a noisy UI.
 */
export function QueuePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedBatchId = searchParams.get("batch");

  const batchesQuery = useQuery({
    queryKey: ["batches"],
    queryFn: () => listBatches(),
    refetchInterval: 5000,
  });

  // Default to the most recent batch when none selected.
  const effectiveBatchId =
    selectedBatchId ??
    (batchesQuery.data && batchesQuery.data.length > 0
      ? batchesQuery.data[0].id
      : null);

  return (
    <div className="max-w-6xl mx-auto px-u-3 py-u-5 grid gap-u-4 md:grid-cols-[260px_1fr]">
      {/* Left: batch list */}
      <aside aria-labelledby="queue-batches-heading" className="space-y-u-2">
        <h2
          id="queue-batches-heading"
          className="text-sm font-semibold text-ink-500 uppercase tracking-wide"
        >
          Batches
        </h2>
        {batchesQuery.isError && batchesQuery.error instanceof BatchApiError && (
          <ErrorPanel error={batchesQuery.error.envelope} />
        )}
        <ul className="space-y-u-1" data-testid="batch-list">
          {(batchesQuery.data ?? []).map((b) => (
            <li key={b.id}>
              <button
                type="button"
                className={`w-full text-left card p-u-2 hover:border-primary transition-colors ${
                  b.id === effectiveBatchId ? "border-primary" : ""
                }`}
                onClick={() => setSearchParams({ batch: b.id })}
                data-testid={`batch-list-item-${b.id}`}
                aria-current={b.id === effectiveBatchId ? "true" : undefined}
              >
                <div className="flex items-center justify-between gap-u-1">
                  <span className="text-sm font-semibold truncate">
                    {b.importer_name}
                  </span>
                  <span className="text-xs text-ink-500 shrink-0">
                    {b.counts.total}
                  </span>
                </div>
                <div className="text-xs text-ink-500 truncate">
                  {b.created_at}
                </div>
                <BatchProgress batch={b} />
              </button>
            </li>
          ))}
          {batchesQuery.data?.length === 0 && !batchesQuery.isLoading && (
            <li className="card p-u-3 text-sm text-ink-500 flex items-center gap-u-1">
              <Inbox size={16} aria-hidden="true" />
              No batches yet.{" "}
              <Link to="/batches/new" className="text-primary underline">
                Submit one
              </Link>
              .
            </li>
          )}
        </ul>
        <div>
          <Link to="/batches/new" className="btn-secondary w-full text-center">
            New batch
          </Link>
        </div>
      </aside>

      {/* Right: selected batch detail */}
      <section className="min-w-0">
        {effectiveBatchId ? (
          <BatchDetailPanel batchId={effectiveBatchId} />
        ) : (
          <div className="card p-u-4 text-ink-500">
            Select a batch to see its applications.
          </div>
        )}
      </section>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Batch detail panel
// ---------------------------------------------------------------------------
function BatchDetailPanel({ batchId }: { batchId: string }) {
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState<"all" | "pending_review" | "approved" | "rejected">(
    "all",
  );

  const detailQuery = useQuery({
    queryKey: ["batch", batchId],
    queryFn: () => getBatch(batchId),
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) return 1500;
      const inflight = data.counts.pending + data.counts.processing;
      return inflight > 0 ? 1500 : false;
    },
  });

  const bulkApprove = useMutation({
    mutationFn: () => bulkApproveBatch(batchId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["batch", batchId] });
      queryClient.invalidateQueries({ queryKey: ["batches"] });
    },
  });

  const filtered = useMemo(() => {
    const apps = detailQuery.data?.applications ?? [];
    if (filter === "all") return apps;
    return apps.filter((a) => a.workflow_status === filter);
  }, [detailQuery.data, filter]);

  if (detailQuery.isLoading) {
    return <div className="card p-u-3 text-ink-500">Loading…</div>;
  }
  if (detailQuery.isError && detailQuery.error instanceof BatchApiError) {
    return <ErrorPanel error={detailQuery.error.envelope} />;
  }
  const detail = detailQuery.data;
  if (!detail) return null;

  const inflight = detail.counts.pending + detail.counts.processing;
  return (
    <div className="space-y-u-3">
      <header className="card p-u-3 space-y-u-1">
        <div className="flex items-baseline justify-between gap-u-2 flex-wrap">
          <h1 className="text-xl font-semibold text-ink-800">
            {detail.importer_name}
          </h1>
          <span className="text-sm text-ink-500">{detail.created_at}</span>
        </div>
        <p className="text-sm text-ink-500">{detail.importer_email}</p>
        {detail.note && (
          <p className="text-sm text-ink-700 italic">{detail.note}</p>
        )}
        <div className="flex items-center gap-u-2 text-sm pt-u-1">
          <CountPill label="Total" value={detail.counts.total} />
          <CountPill label="Approved" value={detail.counts.approved} />
          <CountPill label="Rejected" value={detail.counts.rejected} />
          <CountPill
            label="Needs correction"
            value={detail.counts.needs_correction}
          />
          {inflight > 0 && (
            <span
              className="inline-flex items-center gap-1 text-xs text-ink-500"
              data-testid="inflight-indicator"
            >
              <Clock size={14} aria-hidden="true" />
              {inflight} processing
            </span>
          )}
        </div>
        <div className="flex items-center gap-u-2 pt-u-1">
          <Button
            variant="primary"
            disabled={inflight > 0 || bulkApprove.isPending}
            onClick={() => bulkApprove.mutate()}
            data-testid="bulk-approve"
          >
            <CheckCircle2 size={16} aria-hidden="true" className="inline mr-1" />
            {bulkApprove.isPending ? "Approving\u2026" : "Bulk-approve clean matches"}
          </Button>
          <Button
            variant="ghost"
            onClick={() =>
              queryClient.invalidateQueries({ queryKey: ["batch", batchId] })
            }
            data-testid="refresh-batch"
          >
            <RefreshCcw size={16} aria-hidden="true" className="inline mr-1" />
            Refresh
          </Button>
        </div>
        {bulkApprove.data && (
          <div
            className="card p-u-2 bg-status-match-bg border-status-match-border text-sm"
            data-testid="bulk-approve-result"
          >
            Approved {bulkApprove.data.approved_count}, skipped{" "}
            {bulkApprove.data.skipped_count}.
          </div>
        )}
        {bulkApprove.isError && bulkApprove.error instanceof BatchApiError && (
          <ErrorPanel error={bulkApprove.error.envelope} />
        )}
      </header>

      <div role="tablist" aria-label="Filter applications" className="flex gap-u-1">
        {(
          [
            ["all", "All"],
            ["pending_review", "Pending"],
            ["approved", "Approved"],
            ["rejected", "Rejected"],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={filter === key}
            className={`px-3 py-1 rounded text-sm border ${
              filter === key
                ? "border-primary text-primary bg-white"
                : "border-ink-200 text-ink-500 bg-ink-50"
            }`}
            onClick={() => setFilter(key)}
            data-testid={`filter-${key}`}
          >
            {label}
          </button>
        ))}
      </div>

      <ApplicationsTable applications={filtered} batchId={batchId} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Applications table
// ---------------------------------------------------------------------------
function ApplicationsTable({
  applications,
  batchId,
}: {
  applications: BatchApplication[];
  batchId: string;
}) {
  if (applications.length === 0) {
    return (
      <div className="card p-u-3 text-ink-500">
        No applications match this filter.
      </div>
    );
  }
  return (
    <div className="card overflow-x-auto">
      <table className="w-full text-sm" data-testid="applications-table">
        <thead className="text-left text-ink-500 border-b border-ink-100">
          <tr>
            <th className="px-u-2 py-u-1 font-medium">Serial #</th>
            <th className="px-u-2 py-u-1 font-medium">Brand</th>
            <th className="px-u-2 py-u-1 font-medium">Image</th>
            <th className="px-u-2 py-u-1 font-medium">Pipeline</th>
            <th className="px-u-2 py-u-1 font-medium">Result</th>
            <th className="px-u-2 py-u-1 font-medium">Workflow</th>
            <th className="px-u-2 py-u-1" />
          </tr>
        </thead>
        <tbody>
          {applications.map((a) => {
            const primary =
              a.images.find((img) => img.is_primary) ?? a.images[0] ?? null;
            return (
            <tr
              key={a.id}
              className="border-b border-ink-100 last:border-0 hover:bg-ink-50"
              data-testid={`app-row-${a.id}`}
            >
              <td className="px-u-2 py-u-2 font-mono">
                {a.fields.serial_number}
              </td>
              <td className="px-u-2 py-u-2">{a.fields.brand_name ?? "\u2014"}</td>
              <td
                className="px-u-2 py-u-2 font-mono text-xs text-ink-700 max-w-[14rem] truncate"
                title={primary?.filename ?? undefined}
                data-testid={`app-image-${a.id}`}
              >
                {primary?.filename ?? "\u2014"}
              </td>
              <td className="px-u-2 py-u-2">
                <ProcessingBadge status={a.processing_status} />
              </td>
              <td className="px-u-2 py-u-2">
                {a.analyze ? (
                  <StatusChip status={a.analyze.summary.status} />
                ) : a.error ? (
                  <span className="text-status-mismatch-text text-xs">
                    {a.error.code}
                  </span>
                ) : (
                  <span className="text-ink-400">—</span>
                )}
              </td>
              <td className="px-u-2 py-u-2">
                <WorkflowBadge status={a.workflow_status} />
              </td>
              <td className="px-u-2 py-u-2">
                <Link
                  to={`/queue/applications/${a.id}?batch=${batchId}`}
                  className="text-primary text-sm hover:underline"
                  data-testid={`open-application-${a.id}`}
                >
                  Open
                </Link>
              </td>
            </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Small presentation pieces
// ---------------------------------------------------------------------------
function BatchProgress({ batch }: { batch: Batch }) {
  const c = batch.counts;
  const inflight = c.pending + c.processing;
  const decided = c.approved + c.rejected + c.needs_correction;
  return (
    <div className="text-xs text-ink-500 mt-u-half flex items-center gap-u-1">
      {inflight > 0 ? (
        <>
          <Clock size={12} aria-hidden="true" />
          {inflight} processing
        </>
      ) : (
        <>
          <CheckCircle2 size={12} aria-hidden="true" />
          {decided}/{c.total} decided
        </>
      )}
    </div>
  );
}

function CountPill({ label, value }: { label: string; value: number }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-ink-100 px-2 py-0.5 text-xs text-ink-700">
      <span className="font-mono">{value}</span>
      <span className="text-ink-500">{label}</span>
    </span>
  );
}

function ProcessingBadge({
  status,
}: {
  status: ApplicationProcessingStatus;
}) {
  const cls =
    status === "done"
      ? "text-status-match-text"
      : status === "failed"
      ? "text-status-mismatch-text"
      : "text-ink-500";
  return (
    <span className={`text-xs uppercase tracking-wide ${cls}`}>
      {PROCESSING_STATUS_LABELS[status]}
    </span>
  );
}

function WorkflowBadge({ status }: { status: WorkflowStatus }) {
  const cls =
    status === "approved"
      ? "bg-status-match-bg text-status-match-text border-status-match-border"
      : status === "rejected"
      ? "bg-status-mismatch-bg text-status-mismatch-text border-status-mismatch-border"
      : status === "needs_correction"
      ? "bg-status-review-bg text-status-review-text border-status-review-border"
      : "bg-ink-50 text-ink-700 border-ink-200";
  return (
    <span
      className={`inline-block rounded-full border px-2 py-0.5 text-xs ${cls}`}
    >
      {WORKFLOW_STATUS_LABELS[status]}
    </span>
  );
}
