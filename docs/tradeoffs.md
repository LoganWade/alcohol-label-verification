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
- **PDF multipage handling.** Single-page PDF is supported via image conversion; multipage is deferred.
- **Beverage-type-specific rule packs.** Beer, wine, and spirits each have nuanced TTB requirements. The prototype supports the seven common fields well; full type-specific rule sets are future work.
- **Multi-language OCR.** English only.
- **Mobile-native experience.** The UI is responsive but desktop-first.

## Known limitations of the prototype

- OCR accuracy on highly stylized label typography (script fonts, embossed text, dark-on-dark) is inherently weaker than on clean print. The system surfaces this honestly via per-field confidence and the `Needs Review` / `Uncertain` statuses.
- The Government Warning validator's "header is in all caps" check depends on OCR preserving case. Some OCR engines normalize case; PaddleOCR generally preserves it on labels with strong contrast, but extreme cases will be flagged as `Uncertain`.
- The 5-second budget assumes a typical phone-quality label photo (~2–4 megapixels) on the deployment instance's CPU. Very large images will exceed it; the UI surfaces processing time so reviewers see when this happens.
- Sample data is a mix of synthetic AI-generated labels and public TTB reference imagery. None of it is real submission data.

## Decisions to revisit if this becomes more than a prototype

- Replace the local SQLite review history with a proper database.
- Move OCR to a dedicated worker service so heavy preprocessing doesn't block the API thread.
- Add structured audit logging (who reviewed what, when).
- Add a proper authentication layer with the agency's identity provider.
- Build beverage-type-specific rule packs. See [docs/roadmap.md](./roadmap.md) for the full set of rule-pack, conditional-validator, and legibility-check features identified from a review of the TTB labeling regulations.
- Add a feedback loop so reviewers can mark false matches/mismatches and the thresholds can be tuned with data.
