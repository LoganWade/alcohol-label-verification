import { useEffect, useRef, useState } from "react";
import { FileImage, Upload, X } from "lucide-react";
import { Button } from "@/components/Button";

const MAX_BYTES = 10 * 1024 * 1024;
const ACCEPTED_MIME = ["image/png", "image/jpeg", "image/jpg"];
const ACCEPTED_LABEL = "PNG or JPG up to 10 MB";

interface Props {
  file: File | null;
  onFileChange: (f: File | null) => void;
  onRun: () => void;
  disabled?: boolean;
}

interface ValidateResult {
  ok: boolean;
  error?: string;
}

function validateFile(f: File): ValidateResult {
  if (!ACCEPTED_MIME.includes(f.type)) {
    return {
      ok: false,
      error: `${f.type || "Unknown"} is not supported. Upload a PNG or JPG.`,
    };
  }
  if (f.size > MAX_BYTES) {
    const mb = (f.size / 1024 / 1024).toFixed(1);
    return {
      ok: false,
      error: `That file is ${mb} MB. The limit is 10 MB. Resize and try again.`,
    };
  }
  return { ok: true };
}

export function UploadSection({
  file,
  onFileChange,
  onRun,
  disabled,
}: Props) {
  const [error, setError] = useState<string | undefined>();
  const [isDragging, setIsDragging] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!file) {
      setPreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const handleSelect = (f: File | null) => {
    if (!f) {
      onFileChange(null);
      setError(undefined);
      return;
    }
    const v = validateFile(f);
    if (!v.ok) {
      setError(v.error);
      onFileChange(null);
      return;
    }
    setError(undefined);
    onFileChange(f);
  };

  const onDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
    const f = e.dataTransfer.files?.[0] ?? null;
    handleSelect(f);
  };

  return (
    <section
      aria-labelledby="upload-heading"
      className="card p-u-3 space-y-u-3"
    >
      <header>
        <h2 id="upload-heading" className="text-xl font-semibold">
          Step 2 — Upload the label
        </h2>
        <p className="text-sm text-ink-500 mt-1">
          {ACCEPTED_LABEL}. The image stays on the server only for the
          duration of this review.
        </p>
      </header>

      {!file ? (
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setIsDragging(true);
          }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={onDrop}
          className={`rounded-md border-2 border-dashed p-u-5 text-center transition-colors ${
            isDragging
              ? "border-primary bg-primary-lighter"
              : "border-ink-300 bg-ink-50"
          }`}
          data-testid="dropzone"
        >
          <Upload
            size={32}
            aria-hidden="true"
            className="mx-auto text-ink-400"
          />
          <p className="mt-u-1 text-ink-700 font-medium">
            Drag and drop a label image here
          </p>
          <p className="text-sm text-ink-500">or</p>
          <Button
            variant="secondary"
            onClick={() => inputRef.current?.click()}
            data-testid="button-choose-file"
          >
            Choose a file
          </Button>
          <input
            ref={inputRef}
            type="file"
            accept=".png,.jpg,.jpeg,image/png,image/jpeg"
            className="sr-only"
            onChange={(e) => handleSelect(e.target.files?.[0] ?? null)}
            data-testid="input-file"
          />
          <p className="mt-u-2 text-xs text-ink-500">{ACCEPTED_LABEL}</p>
        </div>
      ) : (
        <div className="border border-ink-200 rounded-md p-u-2 flex items-start gap-u-2">
          {previewUrl ? (
            <img
              src={previewUrl}
              alt={`Preview of ${file.name}`}
              className="w-32 h-32 object-cover rounded border border-ink-200 bg-ink-50"
            />
          ) : (
            <div className="w-32 h-32 rounded border border-ink-200 bg-ink-50 flex items-center justify-center">
              <FileImage
                size={32}
                aria-hidden="true"
                className="text-ink-400"
              />
            </div>
          )}
          <div className="flex-1 min-w-0">
            <p
              className="font-medium text-ink-800 truncate"
              data-testid="text-file-name"
            >
              {file.name}
            </p>
            <p className="text-xs text-ink-500">
              {file.type || "unknown type"} ·{" "}
              {(file.size / 1024).toFixed(0)} KB
            </p>
            <button
              type="button"
              onClick={() => handleSelect(null)}
              className="mt-u-1 inline-flex items-center gap-1 text-sm text-primary hover:underline"
              data-testid="button-remove-file"
            >
              <X size={14} aria-hidden="true" />
              Remove
            </button>
          </div>
        </div>
      )}

      {error && (
        <p
          role="alert"
          className="text-sm text-status-mismatch-text"
          data-testid="text-upload-error"
        >
          {error}
        </p>
      )}

      <div className="flex justify-end">
        <Button
          onClick={onRun}
          disabled={!file || disabled}
          data-testid="button-run-review"
        >
          Run review
        </Button>
      </div>
    </section>
  );
}
