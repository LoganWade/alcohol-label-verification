import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { AlertTriangle, FileText, Image as ImageIcon, Upload } from "lucide-react";

import { Button } from "@/components/Button";
import { Field } from "@/components/Field";
import { ErrorPanel } from "@/components/ErrorPanel";
import { BatchApiError, createBatch } from "@/lib/api/batches";
import type { ManifestError } from "@/lib/types/api";

/**
 * Importer-facing batch upload page.
 *
 * Workflow:
 *   1. Importer fills in their name + email + optional note.
 *   2. Selects a manifest CSV.
 *   3. Selects N image files (one per row in manifest's image_filename column).
 *   4. Submits the form. The page:
 *        - On success: navigates to /queue (analyst queue) with the new id.
 *        - On manifest error: renders the per-row table.
 *        - On other error: renders the standard ErrorPanel.
 *
 * AGENTS.md "Show, don't make me hunt": every selected file is listed back
 * with its size so importers can sanity-check before submitting. Errors
 * cite the row number and column verbatim from the backend response.
 */
export function BatchUploadPage() {
  const navigate = useNavigate();
  const [importerName, setImporterName] = useState("");
  const [importerEmail, setImporterEmail] = useState("");
  const [note, setNote] = useState("");
  const [manifestFile, setManifestFile] = useState<File | null>(null);
  const [imageFiles, setImageFiles] = useState<File[]>([]);
  const [manifestErrors, setManifestErrors] = useState<ManifestError[]>([]);

  const totalImageBytes = useMemo(
    () => imageFiles.reduce((acc, f) => acc + f.size, 0),
    [imageFiles],
  );

  const mutation = useMutation({
    mutationFn: () => {
      if (!manifestFile) {
        throw new Error("Manifest file is required.");
      }
      return createBatch({
        meta: {
          importer_name: importerName.trim(),
          importer_email: importerEmail.trim(),
          note: note.trim() || null,
        },
        manifestFile,
        imageFiles,
      });
    },
    onSuccess: (batch) => {
      // Land on the queue page; the new batch will be at the top.
      navigate(`/queue?batch=${batch.id}`);
    },
    onError: (err) => {
      if (err instanceof BatchApiError) {
        setManifestErrors(err.manifestErrors);
      } else {
        setManifestErrors([]);
      }
    },
  });

  const canSubmit =
    importerName.trim().length > 0 &&
    importerEmail.trim().length > 0 &&
    manifestFile !== null &&
    imageFiles.length > 0 &&
    !mutation.isPending;

  function onAddImages(files: FileList | null) {
    if (!files) return;
    // De-dupe by filename: the backend rejects duplicate image filenames.
    const seen = new Set(imageFiles.map((f) => f.name));
    const next = [...imageFiles];
    for (const f of Array.from(files)) {
      if (!seen.has(f.name)) {
        next.push(f);
        seen.add(f.name);
      }
    }
    setImageFiles(next);
  }

  function onRemoveImage(name: string) {
    setImageFiles((prev) => prev.filter((f) => f.name !== name));
  }

  return (
    <div className="max-w-3xl mx-auto px-u-3 py-u-6">
      <h1 className="text-3xl font-semibold text-ink-800 tracking-tight">
        Submit a batch of applications
      </h1>
      <p className="mt-u-2 text-lg text-ink-600 leading-relaxed">
        Upload a manifest and the label images for each application. Analysts
        will review the batch in the order you submit it; clean matches can be
        approved in bulk once processing finishes.
      </p>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          mutation.mutate();
        }}
        className="mt-u-5 space-y-u-4"
      >
        {/* ---------------- Importer info ---------------- */}
        <fieldset className="space-y-u-3">
          <legend className="text-base font-semibold text-ink-700">
            Importer information
          </legend>
          <Field label="Importer name">
            {({ inputId }) => (
              <input
                id={inputId}
                type="text"
                className="input-base"
                value={importerName}
                onChange={(e) => setImporterName(e.target.value)}
                required
                data-testid="input-importer-name"
              />
            )}
          </Field>
          <Field
            label="Importer email"
            hint="Used for follow-up only — never displayed publicly."
          >
            {({ inputId, describedBy }) => (
              <input
                id={inputId}
                type="email"
                className="input-base"
                value={importerEmail}
                onChange={(e) => setImporterEmail(e.target.value)}
                aria-describedby={describedBy}
                required
                data-testid="input-importer-email"
              />
            )}
          </Field>
          <Field label="Note" optional hint="Any context for the analyst.">
            {({ inputId, describedBy }) => (
              <textarea
                id={inputId}
                className="input-base min-h-[88px]"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                aria-describedby={describedBy}
                rows={3}
                data-testid="input-importer-note"
              />
            )}
          </Field>
        </fieldset>

        {/* ---------------- Manifest ---------------- */}
        <fieldset className="space-y-u-2">
          <legend className="text-base font-semibold text-ink-700">
            Manifest CSV
          </legend>
          <p className="text-sm text-ink-500">
            One row per (application, image). Required columns:{" "}
            <code className="text-xs">serial_number</code>,{" "}
            <code className="text-xs">image_filename</code>,{" "}
            <code className="text-xs">attribution</code>,{" "}
            <code className="text-xs">is_primary</code>. Optional columns
            mirror the COLA application fields.
          </p>
          <label className="card p-u-3 flex items-center gap-u-2 cursor-pointer hover:border-primary">
            <FileText size={20} aria-hidden="true" className="text-primary" />
            <span className="text-sm">
              {manifestFile
                ? `${manifestFile.name} (${formatBytes(manifestFile.size)})`
                : "Choose a CSV file"}
            </span>
            <input
              type="file"
              accept=".csv,text/csv"
              className="sr-only"
              onChange={(e) => setManifestFile(e.target.files?.[0] ?? null)}
              data-testid="input-manifest-file"
            />
          </label>
        </fieldset>

        {/* ---------------- Images ---------------- */}
        <fieldset className="space-y-u-2">
          <legend className="text-base font-semibold text-ink-700">
            Label images
          </legend>
          <p className="text-sm text-ink-500">
            PNG or JPEG. Filenames must match the{" "}
            <code className="text-xs">image_filename</code> column in the
            manifest.
          </p>
          <label className="card p-u-3 flex items-center gap-u-2 cursor-pointer hover:border-primary">
            <ImageIcon size={20} aria-hidden="true" className="text-primary" />
            <span className="text-sm">
              {imageFiles.length === 0
                ? "Choose image files"
                : `${imageFiles.length} file${imageFiles.length === 1 ? "" : "s"} selected (${formatBytes(totalImageBytes)})`}
            </span>
            <input
              type="file"
              accept="image/png,image/jpeg"
              multiple
              className="sr-only"
              onChange={(e) => onAddImages(e.target.files)}
              data-testid="input-images"
            />
          </label>
          {imageFiles.length > 0 && (
            <ul
              data-testid="image-list"
              className="text-sm text-ink-700 divide-y divide-ink-100 border border-ink-100 rounded"
            >
              {imageFiles.map((f) => (
                <li
                  key={f.name}
                  className="flex items-center justify-between px-u-2 py-u-1"
                >
                  <span className="truncate mr-u-2">{f.name}</span>
                  <span className="flex items-center gap-u-2 shrink-0">
                    <span className="text-xs text-ink-500">
                      {formatBytes(f.size)}
                    </span>
                    <button
                      type="button"
                      className="text-xs text-primary hover:underline"
                      onClick={() => onRemoveImage(f.name)}
                      aria-label={`Remove ${f.name}`}
                      data-testid={`remove-image-${f.name}`}
                    >
                      Remove
                    </button>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </fieldset>

        {/* ---------------- Submit ---------------- */}
        <div className="flex items-center gap-u-2">
          <Button
            type="submit"
            disabled={!canSubmit}
            data-testid="submit-batch"
          >
            <Upload size={16} aria-hidden="true" className="inline mr-1" />
            {mutation.isPending ? "Uploading\u2026" : "Submit batch"}
          </Button>
          {!canSubmit && !mutation.isPending && (
            <span className="text-sm text-ink-500">
              Fill out every section above to submit.
            </span>
          )}
        </div>
      </form>

      {/* ---------------- Errors ---------------- */}
      {manifestErrors.length > 0 && (
        <ManifestErrorsTable errors={manifestErrors} />
      )}
      {mutation.isError &&
        manifestErrors.length === 0 &&
        mutation.error instanceof BatchApiError && (
          <div className="mt-u-4">
            <ErrorPanel error={mutation.error.envelope} />
          </div>
        )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

interface ManifestErrorsTableProps {
  errors: ManifestError[];
}

function ManifestErrorsTable({ errors }: ManifestErrorsTableProps) {
  return (
    <div
      role="alert"
      data-testid="manifest-errors"
      className="mt-u-4 card border-status-mismatch-border bg-status-mismatch-bg p-u-3 space-y-u-2"
    >
      <div className="flex items-start gap-u-1">
        <AlertTriangle
          size={20}
          aria-hidden="true"
          className="text-status-mismatch-icon mt-0.5 shrink-0"
        />
        <div>
          <h2 className="text-base font-semibold text-status-mismatch-text">
            Manifest has {errors.length} problem
            {errors.length === 1 ? "" : "s"}
          </h2>
          <p className="text-sm text-ink-700">
            Fix every row listed below and re-upload. Row 0 means a problem
            with the file itself.
          </p>
        </div>
      </div>
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="text-left text-ink-500 border-b border-ink-100">
            <th className="py-u-1 pr-u-2 font-medium">Row</th>
            <th className="py-u-1 pr-u-2 font-medium">Column</th>
            <th className="py-u-1 font-medium">Problem</th>
          </tr>
        </thead>
        <tbody>
          {errors.map((e, idx) => (
            <tr
              key={`${e.row_number}-${e.column ?? "_"}-${idx}`}
              className="border-b border-ink-100 last:border-0"
            >
              <td className="py-u-1 pr-u-2 align-top font-mono">
                {e.row_number}
              </td>
              <td className="py-u-1 pr-u-2 align-top font-mono">
                {e.column ?? "\u2014"}
              </td>
              <td className="py-u-1 align-top">{e.message}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
