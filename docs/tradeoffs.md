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

### Sample-outcomes test gating
`backend/tests/test_sample_outcomes.py` exercises the end-to-end pipeline against the eleven seeded sample scenarios, but the strongest assertions (per-field expected status, governance-warning sub-codes) are gated behind the `real_ocr` pytest marker because the default test run uses the stub OCR provider. Under the stub, the test only asserts that the analysis completes and returns a structurally valid `AnalyzeResponse`. Real-OCR-gated assertions are deferred to a CI job with PaddleOCR weights cached; tracked in the roadmap.

## Decisions to revisit if this becomes more than a prototype

- Replace the local SQLite review history with a proper database.
- Move OCR to a dedicated worker service so heavy preprocessing doesn't block the API thread.
- Add structured audit logging (who reviewed what, when).
- Add a proper authentication layer with the agency's identity provider.
- Build beverage-type-specific rule packs. See [docs/roadmap.md](./roadmap.md) for the full set of rule-pack, conditional-validator, and legibility-check features identified from a review of the TTB labeling regulations.
- Add a feedback loop so reviewers can mark false matches/mismatches and the thresholds can be tuned with data.
