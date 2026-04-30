import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";

import type { AnalyzeError, AnalyzeResponse, ExpectedFields } from "@/lib/types/api";
import { analyzeLabel, AnalyzeApiError } from "@/lib/api/client";
import { getSampleExpectedFields, getSampleImageUrl } from "@/lib/api/samples";
import { STUB_SAMPLE_EXPECTED_FIELDS } from "@/lib/sample";

import { ExpectedFieldsForm } from "@/features/review/ExpectedFieldsForm";
import { expectedFieldsAreReady } from "@/features/review/expectedFieldsValidation";
import { UploadSection } from "@/features/review/UploadSection";
import { ProcessingSection } from "@/features/review/ProcessingSection";
import { ErrorPanel } from "@/components/ErrorPanel";

type Step = "fields" | "upload" | "processing";

// All-null EMPTY: blank fields ship as null on the wire so the backend
// treats them as "not supplied" rather than empty-string mismatches.
// `expectedFieldsAreReady` enforces non-empty required fields before submit.
const EMPTY: ExpectedFields = {
  brand_name: null,
  class_type: null,
  alcohol_content: null,
  net_contents: null,
  bottler: null,
  country_of_origin: null,
  warning: null,
};

/**
 * Determine the initial ExpectedFields value.
 *
 * - ?sample=1         → legacy stub path (Old Tom Distillery) — keeps
 *                       backwards compatibility with the home-page "Try with
 *                       sample data" button from Phase 1.
 * - ?sample=<id>      → fetch from the backend samples API; use EMPTY as
 *                       placeholder while loading.
 * - (no sample param) → EMPTY form.
 */
function initialExpected(sampleParam: string | null): ExpectedFields {
  if (sampleParam === "1") return { ...STUB_SAMPLE_EXPECTED_FIELDS };
  // For any other id we start with EMPTY and let the useQuery below replace it.
  return EMPTY;
}

export function ReviewNewPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const sampleId = searchParams.get("sample");

  // Is this a named sample (anything other than null / "1")?
  const namedSample = sampleId !== null && sampleId !== "1";

  const [expected, setExpected] = useState<ExpectedFields>(() =>
    initialExpected(sampleId),
  );
  const [file, setFile] = useState<File | null>(null);
  const [step, setStep] = useState<Step>("fields");
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [error, setError] = useState<AnalyzeError | null>(null);
  const [uploadWarning, setUploadWarning] = useState<string | undefined>();
  const abortRef = useRef<AbortController | null>(null);

  // -------------------------------------------------------------------------
  // Fetch expected fields from API when ?sample=<id> (not the legacy "1")
  // -------------------------------------------------------------------------
  const { data: sampleFields, isSuccess: sampleFieldsLoaded } =
    useQuery<ExpectedFields>({
      queryKey: ["sample-fields", sampleId],
      queryFn: () => getSampleExpectedFields(sampleId!),
      enabled: namedSample,
    });

  // Prefill expected fields and advance to upload step once loaded
  useEffect(() => {
    if (sampleFieldsLoaded && sampleFields) {
      setExpected(sampleFields);
      setStep("upload");
    }
  }, [sampleFieldsLoaded, sampleFields]);

  // Legacy path: ?sample=1 also advances to upload step
  useEffect(() => {
    if (sampleId === "1") {
      setStep("upload");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // -------------------------------------------------------------------------
  // For named samples, pre-set the file to the sample image so the reviewer
  // can just hit Run without uploading anything. If the prefetch fails for
  // any reason (network, 500, abort), surface a soft warning so the reviewer
  // knows they need to upload manually rather than seeing a silent no-op.
  // -------------------------------------------------------------------------
  useEffect(() => {
    if (!namedSample || !sampleId) return;
    const imageUrl = getSampleImageUrl(sampleId);
    const ctrl = new AbortController();
    void (async () => {
      try {
        const res = await fetch(imageUrl, { signal: ctrl.signal });
        if (!res.ok) {
          setUploadWarning(
            "Sample image is unavailable right now. Choose a label file to continue.",
          );
          return;
        }
        const blob = await res.blob();
        const f = new File([blob], `${sampleId}.png`, { type: "image/png" });
        setFile(f);
        setUploadWarning(undefined);
      } catch (err) {
        // Aborts (component unmount or sampleId change) are expected — stay silent.
        if ((err as Error)?.name === "AbortError") return;
        setUploadWarning(
          "Sample image could not be loaded. Choose a label file to continue.",
        );
      }
    })();
    return () => ctrl.abort();
  }, [namedSample, sampleId]);

  // -------------------------------------------------------------------------
  // Analyze mutation
  // -------------------------------------------------------------------------
  // Typed as `AnalyzeApiError | Error`: analyzeLabel throws AnalyzeApiError
  // for typed envelopes from the API, and bare Error (DOMException with
  // name === "AbortError", or a synthetic "file missing" Error) for
  // local/transport failures. Both are handled in onError below.
  const mutation = useMutation<AnalyzeResponse, AnalyzeApiError | Error>({
    mutationFn: async () => {
      if (!file) throw new Error("file missing");
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      return analyzeLabel({
        image: file,
        expectedFields: expected,
        signal: ctrl.signal,
      });
    },
    onSuccess: (data) => {
      // Pass the File itself via route state. ResultsPage owns creation
      // (and revocation) of the blob: URL; doing it here would let
      // React Strict Mode's dev double-mount revoke the URL between
      // the two mounts, breaking the bbox preview.
      navigate(`/review/${data.review_id}`, {
        state: { response: data, imageFile: file },
      });
    },
    onError: (err) => {
      // Ignore abort — the user clicked Cancel and we just bounce back.
      if (err.name === "AbortError") {
        setStep("upload");
        setStartedAt(null);
        return;
      }
      if (err instanceof AnalyzeApiError) {
        setError(err.envelope);
      } else {
        setError({
          code: "unknown_error",
          message: err.message ?? "Unexpected error.",
          recovery_hint: "Try again. If the issue persists, contact support.",
        });
      }
      setStep("upload");
      setStartedAt(null);
    },
  });

  const handleRun = () => {
    if (!file || !expectedFieldsAreReady(expected)) return;
    setError(null);
    setStartedAt(Date.now());
    setStep("processing");
    // Progress indicator renders at the top of the page; make sure the user
    // actually sees it (Run button can be far below the fold on small screens).
    if (typeof window !== "undefined") {
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
    mutation.mutate();
  };

  const handleCancel = () => {
    abortRef.current?.abort();
    abortRef.current = null;
    setStep("upload");
    setStartedAt(null);
  };

  return (
    <div className="max-w-3xl mx-auto px-u-3 py-u-4 space-y-u-3">
      <h1 className="text-2xl font-semibold">New review</h1>

      {/*
       * Processing indicator is rendered at the TOP of the page (above the
       * form) so progress is always visible without scrolling. The Run button
       * lives at the bottom of Step 2, which is below the fold on small
       * laptops — placing the indicator there hides it from the user.
       */}
      {step === "processing" && startedAt !== null && (
        <ProcessingSection startedAt={startedAt} onCancel={handleCancel} />
      )}

      {error && (
        <ErrorPanel error={error} onRetry={() => setError(null)} />
      )}

      <ExpectedFieldsForm
        value={expected}
        onChange={setExpected}
        onContinue={() => setStep((s) => (s === "fields" ? "upload" : s))}
      />

      {(step === "upload" || step === "processing") && (
        <UploadSection
          file={file}
          onFileChange={setFile}
          onRun={handleRun}
          disabled={step === "processing"}
          warning={uploadWarning}
        />
      )}
    </div>
  );
}
