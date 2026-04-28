import { AlertTriangle } from "lucide-react";
import type { AnalyzeError } from "@/lib/types/api";

interface Props {
  error: AnalyzeError;
  onRetry?: () => void;
}

/**
 * Renders the AnalyzeError envelope's `message` and `recovery_hint` verbatim.
 * AGENTS.md: errors must answer (1) what happened, (2) why, (3) what to do next.
 */
export function ErrorPanel({ error, onRetry }: Props) {
  return (
    <div
      role="alert"
      data-testid="error-panel"
      className="card border-status-mismatch-border bg-status-mismatch-bg p-u-3 space-y-u-1"
    >
      <div className="flex items-start gap-u-1">
        <AlertTriangle
          size={20}
          aria-hidden="true"
          className="text-status-mismatch-icon mt-0.5 shrink-0"
        />
        <div className="space-y-u-half">
          <h2 className="text-base font-semibold text-status-mismatch-text">
            Something went wrong
          </h2>
          <p
            className="text-sm text-status-mismatch-text"
            data-testid="error-message"
          >
            {error.message}
          </p>
          {error.recovery_hint && (
            <p
              className="text-sm text-status-mismatch-text"
              data-testid="error-recovery-hint"
            >
              <span className="font-medium">What to try:</span>{" "}
              {error.recovery_hint}
            </p>
          )}
          <p className="text-xs text-ink-500 mt-1">
            Error code:{" "}
            <code className="font-mono" data-testid="error-code">
              {error.code}
            </code>
          </p>
        </div>
      </div>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="btn-secondary !min-h-[40px]"
          data-testid="error-retry"
        >
          Try again
        </button>
      )}
    </div>
  );
}
