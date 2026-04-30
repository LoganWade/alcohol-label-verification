# Trade-offs

This document records the deliberate choices made during the build, what was deferred, and why. It is intended for an interview reviewer who wants to understand the engineering judgment behind the prototype, not just the code.

## Choices made

### OCR: PaddleOCR local, not a cloud provider
**Why:** Marcus Williams flagged that the federal network blocks outbound traffic to many third-party ML endpoints. The prior vendor pilot suffered from this. A local provider eliminates the failure mode entirely and keeps the 5-second budget achievable.
**Cost:** The PaddleOCR English model weights add ~200MB to the container. Cold starts take longer.
**Mitigation:** Pre-download weights at Docker build time so the runtime image is ready immediately. A health-check ping warms the model after deploy.

### No LLM in the decision path
**Why:** Determinism, latency, defensibility. The "STONE'S THROW vs Stone's Throw" case Dave Morrison cited is solvable with Unicode normalization plus `rapidfuzz` in under a millisecond. An LLM in that position would be slower, non-deterministic, and harder to defend in an interview review or a future compliance review.
**Cost:** Slightly less polished free-text discrepancy summaries.
**Mitigation:** Templated explanation strings for each comparison status. The code path stays open for an LLM-generated summary as a future enhancement, but the decision itself remains deterministic.

### Tiered match status with `Needs Review`, not pass/fail
**Why:** Dave's central feedback was that real-world judgment is needed for benign differences. A binary system would force the prototype to be wrong on cases reviewers handle correctly today.
**Cost:** Reviewers see one more status to interpret.
**Mitigation:** Status vocabulary is fixed (`Match`, `Mismatch`, `Missing`, `Needs Review`, `Uncertain`), each with a one-line plain-language meaning shown in the UI legend.

### Dedicated Government Warning validator
**Why:** Jenny Park described this as the field most often abused — title-case headers, smaller fonts, reworded text. Routing it through the generic comparison would let format violations slip through when wording happens to match.
**Cost:** Duplicated normalization logic between this validator and the generic comparator.
**Mitigation:** Shared normalization utilities in `services/validation/normalizers.py` keep the duplication minimal.

### Single deployable container; monorepo
**Why:** Simplest possible reviewer experience and the smallest possible operational footprint for a prototype. One URL, one log stream, no multi-service orchestration to debug.
**Cost:** Frontend and backend share a release cycle.
**Mitigation:** Acceptable for a take-home; documented as a known limit if the prototype ever evolves.

### Hugging Face Spaces for deployment
**Why:** The Render free tier caps RAM at 512 MB, which causes out-of-memory kills when PaddleOCR loads its English model (~200 MB weights + ~400 MB runtime footprint). Hugging Face Spaces CPU Basic gives 16 GB RAM and 2 vCPUs at no cost, with no credit card required, and is purpose-built for ML demos. The container is auto-built from the repo's `Dockerfile` when `sdk: docker` is set in the README frontmatter. The deployed URL is `https://<user>-<space-name>.hf.space`.
**Cost:** The HF Spaces URL is slightly less polished than a custom domain, and Spaces on the free tier may be paused after a period of inactivity.
**Mitigation:** The first-request warm-up note is in the demo script; the health endpoint pre-warms the OCR model. URL aesthetics are acceptable for a take-home demo.

### React + Vite + TypeScript with a Tailwind subset
**Why:** Fast dev loop, low ceremony, strong typing for the API contract, and a styling system that lets us hew close to USWDS tokens without pulling in the full library.
**Cost:** No native USWDS components; we re-implement the few patterns we need.
**Mitigation:** A small `<StatusChip>` and form component set covers the surface area we need. Spec is to mirror USWDS color and spacing tokens, not to clone the full system.

### Deterministic thresholds in one constants module
**Why:** Inspectability. A reviewer can open one file and see every threshold the system uses. No magic numbers scattered across services.
**Cost:** Minor friction when tuning.
**Mitigation:** Worth it for the audit story.

## Batch upload (feature/batch-upload)

The `feature/batch-upload` branch adds an importer-side bulk submission flow and an analyst queue, motivated by Janet (Seattle) and the recurring "big importers dump 200-300 applications on us at once" pain point.

### Use-case framing: applications, not images
The TTB workflow groups label *images* (front, back, neck, body) into a single COLA *application* with structured fields (Brand Name, Fanciful Name, Net Contents, Alcohol Content, Vintage, etc.). Importers file *applications* in bulk; analysts review *applications* one at a time. "Batch upload" therefore means **N applications submitted in one batch**, not "N images for one application." The latter already works through the existing single-analyze flow.

This framing is what justifies the new `Batch` and `Application` data model below. A simpler "upload N images and run them all" feature would not have moved Janet's needle: she still needs to track which images belong to which application, what the importer claimed about each one, and which she has approved.

### Data model: SQLite (not Postgres, not in-memory)
**Why:** Persistence is non-negotiable — an analyst's bulk-approve action and individual approvals must survive a page refresh and a server restart. SQLite is in the Python stdlib, ships zero ops surface, and runs fine on the HF Spaces ephemeral disk. Postgres would mean a managed-database dependency we cannot justify on free-tier infrastructure for a prototype.
**Cost:** SQLite is single-writer; concurrent batch submissions serialize at the DB layer. The HF Spaces disk is ephemeral, so the database is wiped on container restart — not a problem for a demo, fatal for production.
**Mitigation:** A `BATCH_DB_PATH` environment variable points at the database file, defaulting to `/tmp/alv_batches.db` on HF Spaces. The schema lives in one `migrations.py` module so an upgrade to Postgres later is a single-file change. The deferred review-history feature (already in the roadmap) shares this storage, so this is not net-new accidental complexity.

### Manifest format: CSV, not JSON
**Why:** An importer's compliance team is far more likely to be able to produce CSV out of their existing systems (Excel exports, internal databases, AS/400 reports) than hand-write JSON. Mirroring TTB Step-2 column names (`brand_name`, `fanciful_name`, `net_contents`, `alcohol_content`, `vintage`, `varietals`, `appellation`, `serial_number`, `image_filename`) keeps the cognitive load on the importer's end at zero.
**Cost:** CSV has no nested types, so multi-image-per-application is encoded as multiple rows with the same `serial_number` rather than a JSON array of filenames. We accept this for the prototype.
**Mitigation:** Manifest validation surfaces structured errors in the same `AnalyzeError` envelope shape used by `/analyze`, so the frontend can render line-and-column feedback the importer can act on.

### One image per application gets OCR’d in Phase A
**Why:** TTB allows up to 10 images per application (front, back, neck, body, etc.). Running the full pipeline on every image in a 300-application batch on a free-tier 2-vCPU runtime, with the PaddleOCR thread-safety lock that serializes inference, would mean ~3000 OCR calls behind one lock. At ~2 s per call that is ~100 minutes wall-clock for one batch — not a viable demo.

The importer designates a `primary_image_filename` per application (defaulting to the first image when unspecified). Only the primary image goes through OCR + comparison. Secondary images are stored and shown in the application detail view but not pre-screened.
**Cost:** A real analyst on real labels still wants pre-screening signals on the back-label warning text and the neck-label vintage. We are skipping that.
**Mitigation:** The data model already stores N images per application with attribution types (`front` | `back` | `neck` | `body` | `other`), so wiring the pipeline to additional images later is a config change, not a schema change. Documented in `docs/roadmap.md` as "Phase B: per-image-type pipeline routing."

### Background processing: FastAPI BackgroundTasks, not Celery
**Why:** Celery would mean a Redis broker we cannot run on HF Spaces free tier. FastAPI's built-in `BackgroundTasks` with `asyncio.to_thread` already gets us off the request thread and onto the existing PaddleOCR-locked worker pool. Combined with the SQLite job-status row (`pending` → `processing` → `done` | `failed` per application) the analyst gets a real progress signal.
**Cost:** No retry-with-backoff, no horizontal scale, no dead-letter queue. A batch submitted just before a container restart is lost.
**Mitigation:** The processor is idempotent: re-running on a `pending` application reuses cached OCR results when present. The roadmap captures "Celery + Redis" as the production-grade upgrade path. For a take-home demo with 11 sample labels, the in-process path is honest.

### Bulk-approve clean matches: limited to high-confidence Match-only applications
**Why:** The whole point of pre-screening is that an analyst can disposition the obvious ones in a single click, then spend their attention on the ones that actually need a human. We need a sharp, defensible definition of "obvious": **every** field comparison must be `Match` AND **every** field confidence must be `high`. Anything less and the application stays in the queue for individual review.
**Cost:** This is conservative — a `Match` at `medium` confidence will not be auto-approved, even though a real analyst would have approved it. We choose false negatives (more manual review) over false positives (silent auto-approval of a real defect).
**Mitigation:** The bulk-approve action is logged with the exact field-status snapshot at the moment of approval, so an audit can reconstruct what was approved and on what evidence. The threshold (`Match` + `high` only) lives in `core/constants.py` as `BULK_APPROVE_REQUIRES_CONFIDENCE` so it is a one-line tuning change if we ever want to relax it.

### No real auth or multi-tenancy
**Why:** Out of scope for a take-home prototype. We capture the importer's name and a contact email on the batch as plain text fields. Anyone with the URL can submit batches and see the queue.
**Cost:** Obviously not deployable to a real TTB environment without auth.
**Mitigation:** The `Batch` model already has an `importer_name` and `importer_email` column. Adding real authentication is a single-layer add (e.g. FastAPI dependency that resolves a session to a tenant-scoped DB query); it does not require schema changes.

### Workflow status vocabulary
Applications carry a separate `workflow_status` enum (`pending_review` | `approved` | `rejected` | `needs_correction`) layered on top of the existing `ReviewStatus` from the analysis result. The two are deliberately distinct:
- `ReviewStatus` (analysis result, immutable) reflects what the pipeline found: `Pass` / `Mismatch` / `Needs Review`.
- `workflow_status` (analyst decision, mutable) reflects what the human did about it.

This separation is what lets the bulk-approve action work cleanly: it changes `workflow_status` from `pending_review` to `approved` for applications whose `ReviewStatus` is `Pass` and whose every field is high-confidence Match. The two statuses never collapse into one ambiguous "approved" string.

### Cap on batch size
We cap a single batch at **100 applications** for the prototype. With one OCR call per application at ~2 s on the free tier, a full 100-app batch is ~3.5 minutes wall-clock. The 200-300 number from Janet's quote is honestly outside what one HF Space free-tier instance should be expected to absorb in a single submission — the right answer for that scale is a worker pool, which is in the roadmap. The cap is enforced at the manifest validator and surfaced in the upload UI as a soft warning at 50, hard stop at 100.

## What was deferred

These items were considered and explicitly cut for the time box. Each is structured so it can be added without rearchitecting.

### Stretch features still in scope if time allows
- **Batch upload + queue view.** Sarah and Janet's recurring pain point. The single-review pipeline is reusable; the missing pieces are an upload UI, a job queue, and a results table.
- **Skew/glare/perspective correction.** Jenny's "labels photographed at weird angles" concern. The preprocess stage has the hook; the heavier OpenCV operations and tuning are the work.
- **Review history (SQLite).** Useful for the demo. The data model is small; the work is mostly UI.
- **Seeded sample labels and demo mode.** "Try with sample data" button on the home screen plus 5–6 seeded scenarios.

### Out of scope, intentionally
- **Authentication, user roles, audit logging.** Federal-grade auth is months of work and out of scope for a prototype.
- **COLA integration.** Marcus explicitly said this is a different project entirely.
- **FedRAMP / production compliance posture.** Same reasoning.
- **PDF input.** Not supported in this prototype. The preprocess stage uses Pillow only and does not rasterize PDFs. Adding PDF support requires a rasterizer (PyMuPDF or pdf2image + poppler) plus per-page handling logic; tracked in the roadmap.
- **Beverage-type-specific rule packs.** Beer, wine, and spirits each have nuanced TTB requirements. The prototype supports the seven common fields well; full type-specific rule sets are future work.
- **Multi-language OCR.** English only.
- **Mobile-native experience.** The UI is responsive but desktop-first.

## Known limitations of the prototype

- OCR accuracy on highly stylized label typography (script fonts, embossed text, dark-on-dark) is inherently weaker than on clean print. The system surfaces this honestly via per-field confidence and the `Needs Review` / `Uncertain` statuses.
- The Government Warning validator's "header is in all caps" check depends on OCR preserving case. Some OCR engines normalize case; PaddleOCR generally preserves it on labels with strong contrast, but extreme cases will be flagged as `Uncertain`.
- The 5-second budget assumes a typical phone-quality label photo (~2–4 megapixels) on the deployment instance's CPU. Very large images will exceed it; the UI surfaces processing time so reviewers see when this happens.
- Sample data is a mix of synthetic AI-generated labels and public TTB reference imagery. None of it is real submission data.

## Operational notes

### CORS configuration
The prototype defaults `cors_origins` to localhost ports for Vite dev. The Hugging Face Spaces deployment serves the built frontend and the API from the same origin, so CORS is not in play there. For split deployments (frontend on a CDN, API elsewhere), set `ALV_CORS_ORIGINS` to a JSON array of allowed origins, e.g.:

```
ALV_CORS_ORIGINS='["https://app.example.com","https://staging.example.com"]'
```

`pydantic-settings` parses JSON for complex (list/tuple) fields when the matching env var is set; comma-separated strings are NOT auto-split. Always pass a JSON array, even for a single origin. Verified at runtime.

### Frontend npm audit findings
`npm audit` reports 5 moderate findings against `esbuild` (≤0.24.2) and `vite` (≤6.4.1) in the dev toolchain. The CVEs concern the development server (`vite dev`) accepting cross-origin requests. The production build artifact (`vite build` output served as static files by FastAPI) is unaffected — esbuild and the dev server are not present in the runtime container. Upgrading to Vite 7 / Vitest 3 is on the radar but deferred for take-home scope (config migration + test re-validation). Do not expose `vite dev` to untrusted networks.

### Brand/class-of-fluid heuristic limits
The field-extraction stage uses lightweight token heuristics for `brand_name` and `class_of_fluid` (lines that are mostly title-case, contain known keywords like "VODKA" / "WHISKEY", and are not obviously addresses, ABV strings, government warnings, or net-contents). On clean studio labels this works well, but it is fragile against:

- Stylized brand marks where the brand name is a logotype rendered in a script font (PaddleOCR may emit fragmented or mis-cased tokens).
- Labels where the class of fluid is rendered as ornamental adornment around the brand mark ("FINE - SMALL BATCH - VODKA - DISTILLED" arranged radially).
- Foreign-language adornment phrases ("Distilled & Bottled by", "Estate Reserve") that contain capitalized words but are not the brand.

**Mitigation today:** When confidence is low or extraction fails, the field is reported as `Uncertain` rather than guessed, and the per-field confidence shown in the UI lets reviewers spot weak extractions. The roadmap's Phase 2 "region-aware extraction" replaces these heuristics with layout-anchored extraction (largest text region above the class-of-fluid line, etc.), which is the right long-term fix.

### ResultsPage hard-refresh loses analysis state
Analysis results live in React Router location state (`navigate("/results", { state: result })`). A hard refresh on `/results` drops that state and the page falls back to a "start a new review" prompt. This is intentional for the prototype: persisting result payloads to `sessionStorage` would create a class of stale-result bugs (old result re-rendered for a different image after a partial reload, expired sample images referenced by stale URL, etc.) without a clear win for the demo flow. The proper fix is the deferred review-history feature (SQLite-backed review IDs in the URL), not client-side caching.

### PaddleOCR thread-safety on the free tier
The upstream PaddlePaddle C++ predictor (`paddle::AnalysisPredictor::ZeroCopyRun`) is not thread-safe on a shared `PaddleOCR` instance — documented across [PaddleOCR #11605](https://github.com/PaddlePaddle/PaddleOCR/issues/11605) and [#16238](https://github.com/PaddlePaddle/PaddleOCR/issues/16238). Concurrent `.ocr()` calls produce nondeterministic `SIGSEGV` crashes inside the predictor. The official upstream guidance is "create a separate `PaddleOCR` object per thread," but each instance carries ~600 MB resident memory, which is more than the HF Spaces free tier reliably tolerates with two of them.

**Decision:** serialize `.ocr()` calls behind a process-wide `threading.Lock` in `paddle_ocr.py` and run inference single-threaded (`OMP_NUM_THREADS=1`, `MKL_NUM_THREADS=1`, `cpu_threads=1`). Concurrent reviews queue at the OCR step rather than running in parallel.

**Trade-off:** parallel review throughput is capped at one at a time. On a 2-vCPU box this is not a real loss — two parallel CPU-bound OCR runs would not finish much faster than two sequential ones, and contention on the model weights would slow both. The `asyncio.to_thread` offload in the API layer is preserved, so `/health`, `/samples`, and other lightweight endpoints stay responsive while the OCR queue drains.

If this prototype ever ran on a beefier instance, the right move is the upstream-recommended one: a small worker pool with one `PaddleOCR` instance per worker process (not thread). That removes the lock and unlocks true parallelism, but requires multiple workers' worth of RAM.

**Implication for batch processing:** the batch worker (`backend/app/services/batch/processor.py`) inherits this serialization. A 100-application batch with one OCR call per primary image means up to 100 OCR invocations queued behind the same process-wide lock, each running sequentially at ~2-4 s on the free tier. This is acceptable for the demo (a 100-row batch takes a few minutes) and the queue UI surfaces per-application progress so reviewers see forward motion. On a multi-worker deployment the lock would no longer be the bottleneck — at that point the batch processor should be reworked to dispatch OCR jobs across workers instead of running inside the API process.

### Sample-outcomes test gating
`backend/tests/test_sample_outcomes.py` exercises the end-to-end pipeline against the eleven seeded sample scenarios, but the strongest assertions (per-field expected status, governance-warning sub-codes) are gated behind the `real_ocr` pytest marker because the default test run uses the stub OCR provider. Under the stub, the test only asserts that the analysis completes and returns a structurally valid `AnalyzeResponse`. Real-OCR-gated assertions are deferred to a CI job with PaddleOCR weights cached; tracked in the roadmap.

## Decisions to revisit if this becomes more than a prototype

- Replace the local SQLite review history with a proper database.
- Move OCR to a dedicated worker service so heavy preprocessing doesn't block the API thread.
- Add structured audit logging (who reviewed what, when).
- Add a proper authentication layer with the agency's identity provider.
- Build beverage-type-specific rule packs. See [docs/roadmap.md](./roadmap.md) for the full set of rule-pack, conditional-validator, and legibility-check features identified from a review of the TTB labeling regulations.
- Add a feedback loop so reviewers can mark false matches/mismatches and the thresholds can be tuned with data.
