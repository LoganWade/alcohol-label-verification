import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import type {
  AnalyzeResponse,
  BoundingBox,
  Confidence,
  FieldComparison,
  FieldName,
  WarningValidation,
} from "@/lib/types/api";
import { FIELD_LABELS, FIELD_DISPLAY_ORDER } from "@/lib/types/api";
import { StatusChip } from "@/components/StatusChip";
import { BoundingBoxPreview } from "@/features/review/BoundingBoxPreview";

interface Props {
  response: AnalyzeResponse;
  /**
   * Optional URL of the label image. When present, every evidence panel
   * with a bounding box also renders a cropped preview that highlights
   * the matched region. Omit to fall back to coordinates-only display.
   */
  imageUrl?: string | null;
}

function fmtElapsed(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function fmtBbox(b: BoundingBox | null): string {
  if (!b) return "No bounding box available";
  return `[x0:${b.x0}, y0:${b.y0}, x1:${b.x1}, y1:${b.y1}]`;
}

function ConfidencePill({ confidence }: { confidence: Confidence }) {
  return (
    <span
      className="inline-block rounded-full bg-ink-100 px-2 py-0.5 text-xs text-ink-600 uppercase tracking-wide font-medium"
      data-testid="confidence-pill"
    >
      {confidence}
    </span>
  );
}

interface RowProps {
  fieldName: FieldName;
  comparison: FieldComparison;
  rawText: string | null;
  expanded: boolean;
  onToggle: () => void;
  imageUrl?: string | null;
}

function FieldRow({
  fieldName,
  comparison,
  rawText,
  expanded,
  onToggle,
  imageUrl,
}: RowProps) {
  const Chevron = expanded ? ChevronDown : ChevronRight;
  return (
    <>
      <tr
        className="border-t border-ink-100 hover:bg-ink-50 cursor-pointer"
        onClick={onToggle}
        data-testid={`row-${fieldName}`}
      >
        <td className="px-u-2 py-u-2 align-top">
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onToggle();
            }}
            aria-expanded={expanded}
            aria-controls={`evidence-${fieldName}`}
            className="inline-flex items-center gap-1 font-medium text-ink-800 hover:text-primary"
            data-testid={`toggle-${fieldName}`}
          >
            <Chevron size={16} aria-hidden="true" />
            {FIELD_LABELS[fieldName]}
          </button>
        </td>
        <td className="px-u-2 py-u-2 align-top text-sm">
          {comparison.expected ?? <span className="text-ink-400">—</span>}
        </td>
        <td className="px-u-2 py-u-2 align-top text-sm font-mono">
          {comparison.found_raw ?? <span className="text-ink-400">—</span>}
        </td>
        <td className="px-u-2 py-u-2 align-top">
          <StatusChip status={comparison.status} size="sm" />
        </td>
        <td className="px-u-2 py-u-2 align-top text-xs text-ink-500">
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onToggle();
            }}
            className="text-primary hover:underline"
          >
            {expanded ? "Hide" : "View"}
          </button>
        </td>
      </tr>
      {expanded && (
        <tr
          id={`evidence-${fieldName}`}
          className="bg-ink-50"
          data-testid={`evidence-${fieldName}`}
        >
          <td colSpan={5} className="px-u-2 py-u-2">
            <div className="grid gap-u-2 md:grid-cols-2 text-sm">
              <div>
                <h4 className="font-medium text-ink-700 text-xs uppercase tracking-wide mb-1">
                  Raw OCR text (verbatim)
                </h4>
                <pre className="font-mono text-xs bg-white border border-ink-200 rounded p-2 whitespace-pre-wrap break-words">
{rawText ?? "(none extracted)"}
                </pre>
              </div>
              <div className="space-y-u-1">
                <div>
                  <h4 className="font-medium text-ink-700 text-xs uppercase tracking-wide mb-1">
                    Confidence
                  </h4>
                  <ConfidencePill confidence={comparison.confidence} />
                </div>
                <div>
                  <h4 className="font-medium text-ink-700 text-xs uppercase tracking-wide mb-1">
                    Comparison reason
                  </h4>
                  <p className="text-ink-700">{comparison.reason}</p>
                </div>
                <div>
                  <h4 className="font-medium text-ink-700 text-xs uppercase tracking-wide mb-1">
                    Bounding box
                  </h4>
                  <p className="font-mono text-xs text-ink-600">
                    {fmtBbox(comparison.evidence_bbox)}
                  </p>
                  {comparison.evidence_bbox && imageUrl ? (
                    <div className="mt-u-1">
                      <BoundingBoxPreview
                        bbox={comparison.evidence_bbox}
                        imageUrl={imageUrl}
                        imageAlt={`Label region for ${FIELD_LABELS[fieldName]}`}
                      />
                    </div>
                  ) : (
                    !imageUrl && (
                      <p className="text-xs text-ink-400 italic">
                        Image preview unavailable for this review.
                      </p>
                    )
                  )}
                </div>
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

interface WarningRowProps {
  validation: WarningValidation;
  expanded: boolean;
  onToggle: () => void;
  imageUrl?: string | null;
}

function WarningRow({
  validation,
  expanded,
  onToggle,
  imageUrl,
}: WarningRowProps) {
  const Chevron = expanded ? ChevronDown : ChevronRight;
  const headerOk = validation.header_caps_ok;
  const wordingOk = validation.wording_match;
  return (
    <>
      <tr
        className="border-t-4 border-ink-200 hover:bg-ink-50 cursor-pointer"
        onClick={onToggle}
        data-testid="row-warning"
      >
        <td className="px-u-2 py-u-2 align-top">
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onToggle();
            }}
            aria-expanded={expanded}
            aria-controls="evidence-warning"
            className="inline-flex items-center gap-1 font-medium text-ink-800 hover:text-primary"
            data-testid="toggle-warning"
          >
            <Chevron size={16} aria-hidden="true" />
            Government warning
          </button>
          <div className="mt-1 space-y-0.5 text-xs text-ink-600">
            <p data-testid="warning-header-caps">
              <span className="font-medium">Header all caps:</span>{" "}
              {headerOk ? "Yes" : "No"}
            </p>
            <p data-testid="warning-wording-match">
              <span className="font-medium">Wording matches:</span>{" "}
              {wordingOk ? "Yes" : "No"}
            </p>
            {(!headerOk || !wordingOk) && validation.reason && (
              <p
                className="text-status-mismatch-text mt-1"
                data-testid="warning-reason"
              >
                {validation.reason}
              </p>
            )}
          </div>
        </td>
        <td className="px-u-2 py-u-2 align-top text-sm text-ink-500">
          Statutory text
        </td>
        <td className="px-u-2 py-u-2 align-top text-sm font-mono">
          {validation.raw_text ? (
            <span className="line-clamp-3">{validation.raw_text}</span>
          ) : (
            <span className="text-ink-400">— not detected</span>
          )}
        </td>
        <td className="px-u-2 py-u-2 align-top">
          <StatusChip status={validation.status} size="sm" />
        </td>
        <td className="px-u-2 py-u-2 align-top text-xs text-ink-500">
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onToggle();
            }}
            className="text-primary hover:underline"
          >
            {expanded ? "Hide" : "View"}
          </button>
        </td>
      </tr>
      {expanded && (
        <tr
          id="evidence-warning"
          className="bg-ink-50"
          data-testid="evidence-warning"
        >
          <td colSpan={5} className="px-u-2 py-u-2">
            <div className="grid gap-u-2 md:grid-cols-2 text-sm">
              <div>
                <h4 className="font-medium text-ink-700 text-xs uppercase tracking-wide mb-1">
                  Raw OCR text (verbatim)
                </h4>
                <pre className="font-mono text-xs bg-white border border-ink-200 rounded p-2 whitespace-pre-wrap break-words">
{validation.raw_text ?? "(none extracted)"}
                </pre>
              </div>
              <div className="space-y-u-1">
                <div>
                  <h4 className="font-medium text-ink-700 text-xs uppercase tracking-wide mb-1">
                    Expected text
                  </h4>
                  <pre className="font-mono text-xs bg-white border border-ink-200 rounded p-2 whitespace-pre-wrap break-words">
{validation.expected_text}
                  </pre>
                </div>
                <div>
                  <h4 className="font-medium text-ink-700 text-xs uppercase tracking-wide mb-1">
                    Bounding box
                  </h4>
                  <p className="font-mono text-xs text-ink-600">
                    {fmtBbox(validation.evidence_bbox)}
                  </p>
                  {validation.evidence_bbox && imageUrl && (
                    <div className="mt-u-1">
                      <BoundingBoxPreview
                        bbox={validation.evidence_bbox}
                        imageUrl={imageUrl}
                        imageAlt="Government warning region"
                      />
                    </div>
                  )}
                </div>
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

export function ResultsView({ response, imageUrl }: Props) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const toggle = (key: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  // Index comparisons by field name for ordered render.
  const byField = new Map<FieldName, FieldComparison>();
  response.field_comparisons.forEach((c) => byField.set(c.field, c));

  return (
    <div className="space-y-u-3" aria-live="polite" data-testid="results-view">
      <header className="space-y-u-1">
        <div className="flex flex-wrap items-center gap-u-2">
          <StatusChip
            status={response.summary.status}
            size="lg"
            className="text-base"
          />
          <h1
            className="text-2xl font-semibold text-ink-800"
            data-testid="results-headline"
          >
            {response.summary.headline}
          </h1>
        </div>
        <p
          className="text-sm text-ink-500"
          data-testid="results-elapsed"
        >
          Reviewed in {fmtElapsed(response.processing.elapsed_ms)} ·{" "}
          Image quality:{" "}
          <span className="font-medium">
            {response.processing.image_quality}
          </span>{" "}
          · OCR provider: {response.processing.ocr_provider}
        </p>
      </header>

      <div className="card overflow-hidden">
        <table className="w-full text-left">
          <caption className="sr-only">
            Field-by-field comparison of expected and detected values.
          </caption>
          <thead className="bg-ink-50 text-xs uppercase tracking-wide text-ink-600">
            <tr>
              <th scope="col" className="px-u-2 py-u-1 font-medium">
                Field
              </th>
              <th scope="col" className="px-u-2 py-u-1 font-medium">
                Expected
              </th>
              <th scope="col" className="px-u-2 py-u-1 font-medium">
                Found on label
              </th>
              <th scope="col" className="px-u-2 py-u-1 font-medium">
                Status
              </th>
              <th scope="col" className="px-u-2 py-u-1 font-medium">
                Evidence
              </th>
            </tr>
          </thead>
          <tbody>
            {FIELD_DISPLAY_ORDER.map((fieldName) => {
              const comp = byField.get(fieldName);
              if (!comp) return null;
              const rawText =
                response.extracted_fields[fieldName]?.raw_text ?? null;
              return (
                <FieldRow
                  key={fieldName}
                  fieldName={fieldName}
                  comparison={comp}
                  rawText={rawText}
                  expanded={expanded.has(fieldName)}
                  onToggle={() => toggle(fieldName)}
                  imageUrl={imageUrl}
                />
              );
            })}
            <WarningRow
              validation={response.warning_validation}
              expanded={expanded.has("warning")}
              onToggle={() => toggle("warning")}
              imageUrl={imageUrl}
            />
          </tbody>
        </table>
      </div>

      {response.limitations.length > 0 && (
        <aside
          className="rounded-md border border-ink-200 bg-ink-50 p-u-2 text-xs text-ink-600 space-y-u-half"
          data-testid="limitations"
          aria-label="Limitations"
        >
          <h2 className="text-sm font-semibold text-ink-700">
            Limitations and notes
          </h2>
          <ul className="list-disc pl-5 space-y-0.5">
            {response.limitations.map((l) => (
              <li key={l}>{l}</li>
            ))}
          </ul>
        </aside>
      )}
    </div>
  );
}
