import { useEffect, useState } from "react";
import { Loader2, Check } from "lucide-react";
import { Button } from "@/components/Button";

const STAGES = [
  { id: "preprocess", label: "Reading image" },
  { id: "ocr", label: "Extracting text" },
  { id: "compare", label: "Comparing fields" },
  { id: "warning", label: "Checking warning" },
] as const;

const LONG_RUNNING_MS = 8000;

interface Props {
  startedAt: number;
  onCancel: () => void;
}

function fmt(ms: number): string {
  const s = Math.floor(ms / 1000);
  const mm = Math.floor(s / 60);
  const ss = s % 60;
  return `${mm.toString().padStart(2, "0")}:${ss.toString().padStart(2, "0")}`;
}

/**
 * Processing screen. Backend is synchronous, so we drive the stage indicator
 * from elapsed time rather than reading server-side stage events. The stages
 * roughly cycle over the typical ~3-4s budget; if the request is slower, the
 * last stage stays active and the long-running message appears at 8s.
 */
export function ProcessingSection({ startedAt, onCancel }: Props) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const tick = () => setElapsed(Date.now() - startedAt);
    tick();
    // 250 ms ticks: counter format is second-resolution (mm:ss), so ~4 fps
    // is more than enough. Avoids ~10 re-renders/sec across the route subtree
    // for an OCR run that can take 8–10s on slow hardware.
    const id = window.setInterval(tick, 250);
    return () => window.clearInterval(id);
  }, [startedAt]);

  // Stage activation thresholds (ms): 0, 700, 1800, 3000.
  const stageThresholds = [0, 700, 1800, 3000];
  const activeIdx = stageThresholds.reduce(
    (acc, t, i) => (elapsed >= t ? i : acc),
    0,
  );

  const longRunning = elapsed >= LONG_RUNNING_MS;

  return (
    <section
      aria-labelledby="processing-heading"
      className="card p-u-3 space-y-u-3"
      data-testid="processing-section"
    >
      <header className="flex items-center justify-between flex-wrap gap-u-2">
        <h2 id="processing-heading" className="text-xl font-semibold">
          Reviewing the label…
        </h2>
        <p
          className="font-mono text-sm text-ink-600"
          aria-label="Elapsed time"
          data-testid="elapsed-counter"
        >
          {fmt(elapsed)}
        </p>
      </header>

      <ol
        className="space-y-u-1"
        aria-live="polite"
        aria-atomic="false"
        data-testid="stage-list"
      >
        {STAGES.map((s, i) => {
          const done = i < activeIdx;
          const active = i === activeIdx;
          return (
            <li
              key={s.id}
              className={`flex items-center gap-u-1 text-sm ${
                done
                  ? "text-ink-500"
                  : active
                  ? "text-ink-800 font-medium"
                  : "text-ink-400"
              }`}
              data-stage={s.id}
              data-state={done ? "done" : active ? "active" : "pending"}
            >
              <span
                className={`inline-flex items-center justify-center w-5 h-5 rounded-full border ${
                  done
                    ? "bg-status-match-bg border-status-match-border text-status-match-text"
                    : active
                    ? "bg-primary-lighter border-primary text-primary"
                    : "bg-ink-50 border-ink-200 text-ink-400"
                }`}
                aria-hidden="true"
              >
                {done ? (
                  <Check size={12} strokeWidth={3} />
                ) : active ? (
                  <Loader2 size={12} className="animate-spin" />
                ) : (
                  <span className="block w-1.5 h-1.5 bg-ink-300 rounded-full" />
                )}
              </span>
              <span>{s.label}</span>
              {active && (
                <span className="sr-only">— in progress</span>
              )}
              {done && <span className="sr-only">— complete</span>}
            </li>
          );
        })}
      </ol>

      {longRunning && (
        <p
          className="text-sm text-ink-600 bg-status-review-bg border border-status-review-border rounded-md px-u-2 py-u-1"
          role="status"
          data-testid="long-running-message"
        >
          Taking longer than usual — the image may be low quality.
        </p>
      )}

      <div className="flex justify-end">
        <Button
          variant="secondary"
          onClick={onCancel}
          data-testid="button-cancel"
        >
          Cancel
        </Button>
      </div>
    </section>
  );
}

export { LONG_RUNNING_MS };
