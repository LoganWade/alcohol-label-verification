import { useLocation, useNavigate, Link } from "react-router-dom";
import { Download, Printer, RotateCcw } from "lucide-react";
import type { AnalyzeResponse } from "@/lib/types/api";
import { ResultsView } from "@/features/review/ResultsView";
import { Button } from "@/components/Button";

interface RouteState {
  response?: AnalyzeResponse;
}

export function ResultsPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const state = (location.state as RouteState | null) ?? null;
  const response = state?.response ?? null;

  if (!response) {
    return (
      <div className="max-w-3xl mx-auto px-u-3 py-u-6">
        <h1 className="text-2xl font-semibold">No review loaded</h1>
        <p className="mt-u-1 text-ink-500">
          The review data is held in memory and is not yet stored on the
          server. Open a new review to start over.
        </p>
        <Link to="/" className="btn-primary mt-u-3 inline-flex">
          Back home
        </Link>
      </div>
    );
  }

  const exportJson = () => {
    const blob = new Blob([JSON.stringify(response, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${response.review_id}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="max-w-5xl mx-auto px-u-3 py-u-4 space-y-u-3">
      <ResultsView response={response} />

      <footer className="border-t border-ink-200 pt-u-3 mt-u-3 space-y-u-2 no-print">
        <div className="flex flex-wrap gap-u-1">
          <Button
            variant="primary"
            onClick={() => navigate("/review/new")}
            data-testid="button-run-another"
          >
            <RotateCcw size={16} aria-hidden="true" />
            Run another review
          </Button>
          <Button
            variant="secondary"
            onClick={exportJson}
            data-testid="button-export-json"
          >
            <Download size={16} aria-hidden="true" />
            Export results (JSON)
          </Button>
          <Button
            variant="secondary"
            onClick={() => window.print()}
            data-testid="button-print"
          >
            <Printer size={16} aria-hidden="true" />
            Print
          </Button>
        </div>
      </footer>
    </div>
  );
}
