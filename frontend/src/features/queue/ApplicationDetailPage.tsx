import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, CheckCircle2, RotateCcw, Wrench, XCircle } from "lucide-react";

import { Button } from "@/components/Button";
import { ErrorPanel } from "@/components/ErrorPanel";
import { TextArea } from "@/components/Field";
import { ResultsView } from "@/features/review/ResultsView";
import {
  BatchApiError,
  getApplication,
  getApplicationImageUrl,
  setApplicationDecision,
} from "@/lib/api/batches";
import {
  PROCESSING_STATUS_LABELS,
  WORKFLOW_STATUS_LABELS,
} from "@/lib/types/api";
import type { BatchApplication, WorkflowStatus } from "@/lib/types/api";

/**
 * Per-application detail page used by analysts when an application
 * cannot be bulk-approved (mismatch, missing data, low confidence, etc.).
 *
 * Layout:
 *   - Application header: importer batch link, fields summary, processing
 *     and workflow status.
 *   - Pipeline result: reuses the existing <ResultsView> from the single
 *     image flow when analyze is available; renders <ErrorPanel> on failure;
 *     shows a friendly waiting state while the background processor runs.
 *   - Workflow decision form: 4 status buttons + optional note. Persists
 *     via PUT /applications/{id}/decision.
 */
export function ApplicationDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [searchParams] = useSearchParams();
  const batchHint = searchParams.get("batch");
  const queryClient = useQueryClient();

  const appQuery = useQuery({
    queryKey: ["application", id],
    queryFn: () => getApplication(id as string),
    enabled: !!id,
    refetchInterval: (query) => {
      const data = query.state.data as BatchApplication | undefined;
      if (!data) return 1500;
      const inflight =
        data.processing_status === "pending" ||
        data.processing_status === "processing";
      return inflight ? 1500 : false;
    },
  });

  if (!id) {
    return (
      <div className="max-w-3xl mx-auto px-u-3 py-u-5">
        <ErrorPanel
          error={{
            code: "missing_application_id",
            message: "No application id was provided in the URL.",
            recovery_hint: "Open an application from the queue list.",
          }}
        />
      </div>
    );
  }

  const backTo = batchHint ? `/queue?batch=${batchHint}` : "/queue";

  if (appQuery.isLoading) {
    return (
      <div className="max-w-3xl mx-auto px-u-3 py-u-5">
        <div className="card p-u-3 text-ink-500">Loading application…</div>
      </div>
    );
  }
  if (appQuery.isError && appQuery.error instanceof BatchApiError) {
    return (
      <div className="max-w-3xl mx-auto px-u-3 py-u-5">
        <ErrorPanel error={appQuery.error.envelope} />
      </div>
    );
  }
  const app = appQuery.data;
  if (!app) return null;

  const onMutated = (updated: BatchApplication) => {
    queryClient.setQueryData(["application", id], updated);
    queryClient.invalidateQueries({ queryKey: ["batch", app.batch_id] });
    queryClient.invalidateQueries({ queryKey: ["batches"] });
  };

  return (
    <div className="max-w-4xl mx-auto px-u-3 py-u-5 space-y-u-3">
      <div className="flex items-center gap-u-2 text-sm">
        <Link
          to={backTo}
          className="text-primary hover:underline inline-flex items-center gap-1"
          data-testid="back-to-queue"
        >
          <ArrowLeft size={14} aria-hidden="true" />
          Back to queue
        </Link>
      </div>

      <ApplicationHeader app={app} />

      <PipelineSection app={app} />

      <DecisionForm app={app} onMutated={onMutated} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Header
// ---------------------------------------------------------------------------
function ApplicationHeader({ app }: { app: BatchApplication }) {
  const f = app.fields;
  const rows: Array<[string, string | null]> = [
    ["Serial #", f.serial_number],
    ["Brand name", f.brand_name],
    ["Fanciful name", f.fanciful_name],
    ["Class / type", f.class_type],
    ["Alcohol content", f.alcohol_content],
    ["Net contents", f.net_contents],
    ["Bottler", f.bottler],
    ["Country of origin", f.country_of_origin],
  ];
  return (
    <header className="card p-u-3 space-y-u-2" data-testid="application-header">
      <div className="flex items-baseline justify-between gap-u-2 flex-wrap">
        <h1 className="text-xl font-semibold text-ink-800">
          Application {f.serial_number}
        </h1>
        <div className="flex items-center gap-u-1 text-xs">
          <span
            className="rounded-full bg-ink-100 px-2 py-0.5 text-ink-700"
            data-testid="processing-pill"
          >
            {PROCESSING_STATUS_LABELS[app.processing_status]}
          </span>
          <span
            className="rounded-full bg-ink-100 px-2 py-0.5 text-ink-700"
            data-testid="workflow-pill"
          >
            {WORKFLOW_STATUS_LABELS[app.workflow_status]}
          </span>
        </div>
      </div>
      <dl className="grid grid-cols-2 gap-x-u-3 gap-y-u-1 text-sm">
        {rows.map(([label, value]) => (
          <div key={label} className="flex flex-col">
            <dt className="text-ink-500 text-xs uppercase tracking-wide">
              {label}
            </dt>
            <dd className="text-ink-800">{value ?? "—"}</dd>
          </div>
        ))}
      </dl>
      {app.images.length > 0 && (
        <div className="text-xs text-ink-500">
          {app.images.length} image{app.images.length === 1 ? "" : "s"}:{" "}
          {app.images.map((img) => img.filename).join(", ")}
        </div>
      )}
    </header>
  );
}

// ---------------------------------------------------------------------------
// Pipeline section
// ---------------------------------------------------------------------------
function PipelineSection({ app }: { app: BatchApplication }) {
  if (app.processing_status === "pending" || app.processing_status === "processing") {
    return (
      <div
        className="card p-u-3 text-ink-500"
        data-testid="pipeline-waiting"
      >
        Pipeline is still running. This page refreshes automatically.
      </div>
    );
  }
  if (app.processing_status === "failed" && app.error) {
    return <ErrorPanel error={app.error} />;
  }
  if (app.analyze) {
    // Prefer the primary image; fall back to the first image if no
    // image has been flagged primary (the manifest parser should
    // prevent that, but we render defensively).
    const previewImage =
      app.images.find((img) => img.is_primary) ?? app.images[0] ?? null;
    const imageUrl = previewImage
      ? getApplicationImageUrl(app.id, previewImage.id)
      : null;
    return <ResultsView response={app.analyze} imageUrl={imageUrl} />;
  }
  return (
    <div className="card p-u-3 text-ink-500" data-testid="pipeline-empty">
      No pipeline result is available for this application yet.
    </div>
  );
}

// ---------------------------------------------------------------------------
// Decision form
// ---------------------------------------------------------------------------
const DECISION_BUTTONS: Array<{
  status: WorkflowStatus;
  label: string;
  icon: typeof CheckCircle2;
}> = [
  { status: "approved", label: "Approve", icon: CheckCircle2 },
  { status: "rejected", label: "Reject", icon: XCircle },
  { status: "needs_correction", label: "Needs correction", icon: Wrench },
  { status: "pending_review", label: "Reset to pending", icon: RotateCcw },
];

function DecisionForm({
  app,
  onMutated,
}: {
  app: BatchApplication;
  onMutated: (updated: BatchApplication) => void;
}) {
  const [note, setNote] = useState(app.decided_note ?? "");

  const decision = useMutation({
    mutationFn: (status: WorkflowStatus) =>
      setApplicationDecision(app.id, {
        workflow_status: status,
        note: note.trim() ? note.trim() : null,
      }),
    onSuccess: (updated) => {
      onMutated(updated);
    },
  });

  return (
    <form
      className="card p-u-3 space-y-u-2"
      data-testid="decision-form"
      onSubmit={(e) => e.preventDefault()}
    >
      <h2 className="text-sm font-semibold text-ink-500 uppercase tracking-wide">
        Workflow decision
      </h2>
      <TextArea
        label="Note"
        hint="Optional. Captured with the decision and shown to the importer."
        optional
        value={note}
        onChange={(e) => setNote(e.target.value)}
        rows={3}
        data-testid="decision-note"
      />
      <div className="flex flex-wrap items-center gap-u-1">
        {DECISION_BUTTONS.map(({ status, label, icon: Icon }) => {
          const active = app.workflow_status === status;
          return (
            <Button
              key={status}
              type="button"
              variant={
                status === "approved"
                  ? "primary"
                  : status === "rejected"
                  ? "secondary"
                  : "ghost"
              }
              disabled={decision.isPending}
              onClick={() => decision.mutate(status)}
              data-testid={`decision-${status}`}
              aria-pressed={active}
            >
              <Icon size={16} aria-hidden="true" className="inline mr-1" />
              {label}
              {active && (
                <span className="ml-1 text-xs text-ink-500">(current)</span>
              )}
            </Button>
          );
        })}
      </div>
      {decision.isError && decision.error instanceof BatchApiError && (
        <ErrorPanel error={decision.error.envelope} />
      )}
      {decision.isSuccess && (
        <p
          className="text-sm text-status-match-text"
          data-testid="decision-success"
        >
          Saved.
        </p>
      )}
    </form>
  );
}
