import { Link, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  Upload,
  Sparkles,
  FlaskConical,
  BookOpen,
  PackagePlus,
  ClipboardList,
} from "lucide-react";

import type { SampleSummary, BatchSampleSummary } from "@/lib/types/api";
import { listSamples, listBatchSamples } from "@/lib/api/samples";

/**
 * Home screen — one main action (start review) plus grouped demo samples.
 *
 * Samples are fetched from the backend and split into two visual sections:
 *   - "Synthetic test scenarios" (provenance === "synthetic")
 *   - "TTB reference labels" (provenance === "public_ttb_reference")
 *
 * AGENTS.md: "Present one main action per screen." The Start Review card is
 * the primary CTA; the sample sections are secondary and labelled clearly.
 */
export function HomePage() {
  const navigate = useNavigate();

  const { data: samples = [], isLoading: samplesLoading } = useQuery<
    SampleSummary[]
  >({
    queryKey: ["samples"],
    queryFn: listSamples,
  });

  const { data: batchSamples = [], isLoading: batchSamplesLoading } = useQuery<
    BatchSampleSummary[]
  >({
    queryKey: ["batch-samples"],
    queryFn: listBatchSamples,
  });

  const synthetic = samples.filter((s) => s.provenance === "synthetic");
  const ttbRef = samples.filter(
    (s) => s.provenance === "public_ttb_reference",
  );
  const syntheticBatch = batchSamples.filter(
    (s) => s.provenance === "synthetic",
  );

  const hasSynthetic = synthetic.length > 0 || syntheticBatch.length > 0;
  const hasAnySamples = samples.length > 0 || batchSamples.length > 0;
  const isLoading = samplesLoading || batchSamplesLoading;

  return (
    <div className="max-w-3xl mx-auto px-u-3 py-u-6">
      <h1 className="text-3xl font-semibold text-ink-800 tracking-tight">
        Verify a label against the application data.
      </h1>
      <p className="mt-u-2 text-lg text-ink-600 leading-relaxed">
        Upload a label image and your expected fields. The reviewer-assist tool
        will compare them and highlight anything that needs a closer look.
      </p>

      {/* ---- Primary action ---- */}
      <div className="mt-u-5">
        <Link
          to="/review/new"
          className="card p-u-3 hover:border-primary hover:shadow-sm transition-all flex flex-col gap-u-1 group"
          data-testid="link-start-review"
        >
          <Upload size={28} aria-hidden="true" className="text-primary" />
          <h2 className="text-lg font-semibold">Start a label review</h2>
          <p className="text-sm text-ink-500">
            Enter expected fields, upload an image, and run the review.
          </p>
          <span className="mt-auto inline-flex items-center gap-1 text-primary font-medium group-hover:underline">
            Begin <ArrowRight size={16} aria-hidden="true" />
          </span>
        </Link>
      </div>

      {/* ---- Batch upload secondary actions ---- */}
      <div className="mt-u-3 grid gap-u-2 sm:grid-cols-2">
        <Link
          to="/batches/new"
          className="card p-u-3 hover:border-primary hover:shadow-sm transition-all flex flex-col gap-u-1 group"
          data-testid="link-batch-upload"
        >
          <PackagePlus size={24} aria-hidden="true" className="text-primary" />
          <h2 className="text-base font-semibold">Submit a batch</h2>
          <p className="text-sm text-ink-500">
            Importer flow: upload a manifest CSV plus one image per
            application.
          </p>
          <span className="mt-auto inline-flex items-center gap-1 text-primary text-sm font-medium group-hover:underline">
            New batch <ArrowRight size={14} aria-hidden="true" />
          </span>
        </Link>
        <Link
          to="/queue"
          className="card p-u-3 hover:border-primary hover:shadow-sm transition-all flex flex-col gap-u-1 group"
          data-testid="link-analyst-queue"
        >
          <ClipboardList
            size={24}
            aria-hidden="true"
            className="text-primary"
          />
          <h2 className="text-base font-semibold">Open analyst queue</h2>
          <p className="text-sm text-ink-500">
            Analyst flow: review batches and bulk-approve clean matches.
          </p>
          <span className="mt-auto inline-flex items-center gap-1 text-primary text-sm font-medium group-hover:underline">
            View queue <ArrowRight size={14} aria-hidden="true" />
          </span>
        </Link>
      </div>

      {/* ---- Sample sections ---- */}
      {!isLoading && hasAnySamples && (
        <div className="mt-u-6 space-y-u-5">
          {/* Synthetic test scenarios */}
          {hasSynthetic && (
            <section aria-labelledby="section-synthetic">
              <div className="flex items-center gap-u-1 mb-u-2">
                <FlaskConical
                  size={18}
                  aria-hidden="true"
                  className="text-ink-400"
                />
                <h2
                  id="section-synthetic"
                  className="text-sm font-semibold text-ink-500 uppercase tracking-wide"
                >
                  Synthetic test scenarios
                </h2>
              </div>
              <div
                className="grid gap-u-2 sm:grid-cols-2"
                data-testid="sample-group-synthetic"
              >
                {synthetic.map((sample) => (
                  <SampleCard
                    key={sample.id}
                    sample={sample}
                    onClick={() =>
                      navigate(`/review/new?sample=${sample.id}`)
                    }
                  />
                ))}
                {syntheticBatch.map((sample) => (
                  <BatchSampleCard
                    key={sample.id}
                    sample={sample}
                    onClick={() =>
                      navigate(`/batches/new?sample=${sample.id}`)
                    }
                  />
                ))}
              </div>
            </section>
          )}

          {/* TTB reference labels */}
          {ttbRef.length > 0 && (
            <section aria-labelledby="section-ttb">
              <div className="flex items-center gap-u-1 mb-u-2">
                <BookOpen
                  size={18}
                  aria-hidden="true"
                  className="text-ink-400"
                />
                <h2
                  id="section-ttb"
                  className="text-sm font-semibold text-ink-500 uppercase tracking-wide"
                >
                  TTB reference labels
                </h2>
              </div>
              <div
                className="grid gap-u-2 sm:grid-cols-2"
                data-testid="sample-group-ttb"
              >
                {ttbRef.map((sample) => (
                  <SampleCard
                    key={sample.id}
                    sample={sample}
                    onClick={() =>
                      navigate(`/review/new?sample=${sample.id}`)
                    }
                  />
                ))}
              </div>
            </section>
          )}
        </div>
      )}

      {/* Loading skeleton — only while the list is fetching */}
      {isLoading && (
        <div className="mt-u-6 space-y-u-2" aria-busy="true" aria-label="Loading samples">
          {[1, 2].map((n) => (
            <div
              key={n}
              className="card p-u-3 animate-pulse"
              aria-hidden="true"
            >
              <div className="h-4 bg-ink-100 rounded w-1/3 mb-u-1" />
              <div className="h-3 bg-ink-100 rounded w-2/3" />
            </div>
          ))}
        </div>
      )}

      <div className="mt-u-6 text-sm text-ink-500 max-w-prose">
        <p>
          This prototype runs entirely on local infrastructure. Uploaded images
          are processed in memory and not stored beyond the demo session.
        </p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// SampleCard sub-component
// ---------------------------------------------------------------------------

interface SampleCardProps {
  sample: SampleSummary;
  onClick: () => void;
}

function SampleCard({ sample, onClick }: SampleCardProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="card p-u-3 text-left hover:border-primary hover:shadow-sm transition-all flex flex-col gap-u-1 group"
      data-testid={`link-try-sample-${sample.id}`}
    >
      <Sparkles size={20} aria-hidden="true" className="text-primary" />
      <h3 className="text-base font-semibold leading-snug">{sample.title}</h3>
      <p className="text-sm text-ink-500 flex-1">{sample.description}</p>
      <p className="text-xs text-ink-400 italic">{sample.expected_outcome}</p>
      <span className="mt-auto inline-flex items-center gap-1 text-primary text-sm font-medium group-hover:underline">
        Load sample <ArrowRight size={14} aria-hidden="true" />
      </span>
    </button>
  );
}

// ---------------------------------------------------------------------------
// BatchSampleCard sub-component
// ---------------------------------------------------------------------------

interface BatchSampleCardProps {
  sample: BatchSampleSummary;
  onClick: () => void;
}

function BatchSampleCard({ sample, onClick }: BatchSampleCardProps) {
  const appCount = sample.image_filenames.length;
  return (
    <button
      type="button"
      onClick={onClick}
      className="card p-u-3 text-left hover:border-primary hover:shadow-sm transition-all flex flex-col gap-u-1 group"
      data-testid={`link-try-batch-sample-${sample.id}`}
    >
      <div className="flex items-center gap-u-1">
        <PackagePlus size={20} aria-hidden="true" className="text-primary" />
        <span className="text-xs font-semibold uppercase tracking-wide text-primary">
          Batch · {appCount} app{appCount === 1 ? "" : "s"}
        </span>
      </div>
      <h3 className="text-base font-semibold leading-snug">{sample.title}</h3>
      <p className="text-sm text-ink-500 flex-1">{sample.description}</p>
      <p className="text-xs text-ink-400 italic">{sample.expected_outcome}</p>
      <span className="mt-auto inline-flex items-center gap-1 text-primary text-sm font-medium group-hover:underline">
        Load batch sample <ArrowRight size={14} aria-hidden="true" />
      </span>
    </button>
  );
}
