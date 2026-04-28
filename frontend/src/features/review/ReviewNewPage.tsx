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

const EMPTY: ExpectedFields = {
  brand_name: "",
  class_type: "",
  alcohol_content: "",
  net_contents: "",
  bottler: "",
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
  // can just hit Run without uploading anything.
  // -------------------------------------------------------------------------
  useEffect(() => {
    if (!namedSample || !sampleId) return;
    const imageUrl = getSampleImageUrl(sampleId);
    // Fetch the PNG and wrap in a File object so the existing upload path
    // (which calls analyzeLabel with a File) works unchanged.
    void (async () => {
      try {
        const res = await fetch(imageUrl);
        if (!res.ok) return;
        const blob = await res.blob();
        const f = new File([blob], `${sampleId}.png`, { type: "image/png" });
        setFile(f);
      } catch {
        // Non-fatal — user can still upload their own image.
      }
    })();
  }, [namedSample, sampleId]);

  // -------------------------------------------------------------------------
  // Analyze mutation
  // -------------------------------------------------------------------------
  const mutation = useMutation<AnalyzeResponse, unknown>({
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
      navigate(`/review/${data.review_id}`, { state: { response: data } });
    },
    onError: (err) => {
      // Ignore abort — the user clicked Cancel and we just bounce back.
      if ((err as Error)?.name === "AbortError") {
        setStep("upload");
        setStartedAt(null);
        return;
      }
      if (err instanceof AnalyzeApiError) {
        setError(err.envelope);
      } else {
        setError({
          code: "unknown_error",
          message: (err as Error)?.message ?? "Unexpected error.",
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
        />
      )}

      {step === "processing" && startedAt !== null && (
        <ProcessingSection startedAt={startedAt} onCancel={handleCancel} />
      )}
    </div>
  );
}
