# Architecture

This document captures the design of the AI-Powered Alcohol Label Verification prototype, the reasoning behind the major decisions, and the contracts between components. It should be readable by an interview reviewer in roughly ten minutes.

## 1. Restated scope

Build a standalone prototype that helps a TTB compliance reviewer verify, for a single alcohol label image, whether:

- The fields on the label (brand, class/type, ABV/proof, net contents, bottler/producer, country of origin) match the expected values from the corresponding application.
- The mandatory Government Health Warning Statement is present, worded correctly, and formatted with an all-caps "GOVERNMENT WARNING:" header.

The prototype is **not** a COLA integration, **not** an authoritative compliance decision, and **not** a production system. It is a proof of concept that proposes how AI-assisted review *could* fit into the agency's workflow.

## 2. Design constraints and where they come from

| Constraint | Source | Architectural consequence |
|---|---|---|
| Single-label analysis ≈ 5 seconds | Sarah Chen — prior vendor took 30–40s and the team abandoned it | Local OCR only; no chained LLM calls; preprocessing budget capped |
| Outbound network unreliable | Marcus Williams — federal firewalls block third-party ML endpoints | No cloud OCR, no remote LLM in the decision path |
| Reviewers vary widely in tech comfort | Sarah Chen, Dave Morrison | Single linear flow, plain language, no jargon, large targets |
| Reviewers need to see judgment, not be replaced | Dave Morrison — the "STONE'S THROW vs Stone's Throw" example | Tiered match status with raw evidence one click away; never the words "approved" or "rejected" |
| Government Warning is strict and easily abused | Jenny Park — has seen title-case warnings, smaller fonts, reworded text | Dedicated validator independent of the generic comparison stage |
| Batch processing is a real pain point | Sarah Chen, Janet (Seattle) — 200–300 labels at peak | Batch flow as a stretch feature, sharing the single-review pipeline |
| Take-home time box | Assignment | Boring, dependable choices over clever ones; one provider per layer with a clean abstraction for swap-in later |

## 3. High-level architecture

```text
┌──────────────────────────────────────────────────────────────────────┐
│                         Browser (React + Vite)                       │
│                                                                      │
│   Home  →  Expected fields  →  Upload  →  Processing  →  Results     │
│                                                                      │
└─────────────────────┬────────────────────────────────────────────────┘
                      │ multipart/form-data: image + expected_fields JSON
                      ▼
┌──────────────────────────────────────────────────────────────────────┐
│                       FastAPI backend (Python 3.11)                  │
│                                                                      │
│   POST /api/v1/reviews/analyze                                       │
│        │                                                             │
│        ▼                                                             │
│   ┌─────────────────────  Extraction pipeline  ──────────────────┐   │
│   │  1. Preprocess     (OpenCV + Pillow)                          │   │
│   │  2. OCR            (PaddleOCR — local, no outbound)           │   │
│   │  3. Region attribution                                        │   │
│   │  4. Field extraction (deterministic parsers + heuristics)     │   │
│   └─────────────────────────────┬─────────────────────────────────┘   │
│                                 ▼                                    │
│   ┌─────────────────────  Validation  ───────────────────────────┐   │
│   │  5. Comparison        (rapidfuzz + normalization, tiered)    │   │
│   │  6. Warning validator (dedicated, exact-text + format)       │   │
│   └─────────────────────────────┬─────────────────────────────────┘   │
│                                 ▼                                    │
│   ┌─────────────────────  Reporting  ────────────────────────────┐   │
│   │  7. Aggregate response: fields, comparisons, warning,        │   │
│   │     summary, processing metadata, limitations                │   │
│   └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│   Batch subsystem (POST /api/v1/batches → CSV manifest +             │
│   N images → BackgroundTasks worker → analyst queue + bulk           │
│   approve). Reuses the same pipeline above, one app at a time,       │
│   serialized behind the process-wide PaddleOCR lock.                 │
│                                                                      │
│   SQLite — batch + application state, plus seeded sample             │
│   manifests (synthetic + TTB reference labels).                      │
└──────────────────────────────────────────────────────────────────────┘
```

Single deployable container. Frontend is built statically and served by the same backend (or fronted by a static host); there is no separate API gateway, queue, or microservice.

## 4. Pipeline stages in detail

Each stage is a separate Python module under `backend/app/services/` with typed Pydantic input and output models, an explicit confidence or quality indicator, and its own unit tests. Stages do not mutate each other's outputs.

### 4.1 Preprocess
**Input:** raw uploaded image bytes.
**Output:** preprocessed image array + `ImageQualityReport` (resolution, blur score, estimated skew angle, contrast score, overall quality tier).
**Operations:** EXIF rotation fix → quality metrics (blur via Laplacian variance, contrast via grayscale std-dev) → skew estimation via `cv2.minAreaRect` on a Canny edge mask → **deskew rotation** when `|estimated_skew| ≥ 1.0°` (canvas expanded with white fill, bicubic resampling, no clipping) → resize to a target long edge → PNG encode for OCR. Optional perspective correction is a stretch goal.
**Why deskew matters:** PaddleOCR's line detector drops entire lines on photos rotated more than a few degrees. The seeded `skewed_lowlight` sample (7° rotation) went from "warning header only" to the full warning paragraph being captured after deskew was added.
**Budget:** ~300ms typical.

### 4.2 OCR
**Input:** preprocessed image.
**Output:** list of `OcrToken { text, bbox, confidence }`.
**Provider:** PaddleOCR (English) running locally. Behind an `ExtractionProvider` interface so a Tesseract fallback or future cloud provider can be swapped in without touching downstream stages.
**Rule:** the raw token text is **evidence** and is never mutated. Normalization happens later, on copies.
**Budget:** ~2–3s typical.

### 4.3 Region attribution
**Input:** OCR tokens + label-pattern heuristics.
**Output:** `FieldCandidates { brand, class_type, abv, net_contents, bottler, country_of_origin, warning }`, each containing zero or more candidate token clusters with provenance (which tokens, which bbox).
**Approach:** spatial heuristics (top region usually carries brand; bottom region usually carries warning) plus regex anchors (e.g. `\d+(\.\d+)?\s*%\s*(alc|alcohol)` for ABV, `GOVERNMENT WARNING` as the warning anchor).
**Budget:** <100ms.

### 4.4 Field extraction
**Input:** field candidates.
**Output:** `ExtractedFields` — a single best value per field plus the candidate list and a per-field confidence (`high | medium | low | uncertain`).
**Approach:** deterministic parsers for structured fields (ABV/proof normalization, net contents unit conversion); best-candidate selection for free-text fields (highest OCR confidence within the expected region).
**Budget:** <100ms.

### 4.5 Comparison
**Input:** `ExtractedFields` + `ExpectedFields`.
**Output:** `FieldComparison[]` — one entry per field with `expected`, `found_raw`, `found_normalized`, `status`, `reason`, `evidence_bbox`, and `confidence`.
**Status values:** `Match`, `Mismatch`, `Missing`, `Needs Review`, `Uncertain` (the fixed vocabulary defined in AGENTS.md).
**Algorithm:**
1. Unicode NFKC normalization on copies.
2. Case-fold, collapse whitespace, normalize quotes/dashes.
3. If equal post-normalization → `Match` (with a "normalized" note when the raw values differed).
4. Word-set equality (lowercase alphanumeric tokens, apostrophes stripped). If both sides have the same word set, the only differences are punctuation/whitespace formatting noise → `Match`. This is what catches `STONE'S THROW WINERY` vs `STONES THROW WINERY` without false-flagging it as a typo.
5. Otherwise compute `rapidfuzz.fuzz.ratio` (character-level Levenshtein) on the normalized strings:
   - ≥98 → `Match`
   - 80–97 → `Needs Review`
   - <80 → `Mismatch`
6. If OCR confidence on the underlying tokens is `low`, downgrade `Match` to `Needs Review` (uncertainty propagates).
7. If no candidate exists for a required field → `Missing`.

We deliberately use `fuzz.ratio` (character-level) instead of `fuzz.token_set_ratio` for tier 5: `token_set_ratio` deduplicates and intersects tokens, so it scored `STONE'S THROW WINERY` vs `STONE'S THROW WINEERY` at 97.6 (above the match threshold) and `Cabernet Sauvignon` vs `Cabernet Sauvignon Reserve` at 100 — both clear failure modes for this domain. `fuzz.ratio` penalizes intra-word edits and missing/extra tokens proportionally.

The Government Warning validator (§4.6) keeps its own threshold and still uses `token_set_ratio`, because a long statutory paragraph wants whole-paragraph word coverage and is genuinely tolerant of word-order/whitespace noise.

All thresholds live in a single constants module so they are inspectable, testable, and tunable without scattering magic numbers.

### 4.6 Warning validation
A dedicated, opinionated validator — never the generic comparison stage. The Government Warning is the field most often abused on real labels (Jenny's testimony) and the field most consequential for compliance.

**Checks performed:**
1. **Presence:** is `GOVERNMENT WARNING` (any case) detected anywhere in the OCR output?
2. **Header format:** is the literal string `GOVERNMENT WARNING` in all caps?
3. **Wording:** does the body match the expected statutory text after normalization?
4. **Confidence guard:** if the warning region's OCR confidence is poor, return `Uncertain` with a reason rather than declaring a match or a fail.

**Output:** `WarningValidation { status, header_caps_ok, wording_match, evidence_bbox, raw_text, reason }`.

### 4.7 Reporting
Aggregates everything into the API response, computes the overall summary status (`Pass`, `Mismatch`, `Needs Review`, depending on the worst per-field outcome), and attaches processing metadata (per-stage timing, image quality tier, model versions) and a `limitations` array surfacing anything reviewers should know.

## 5. API contract

### `POST /api/v1/reviews/analyze`

**Request:** `multipart/form-data`
- `image`: file (PNG or JPG; PDF support is on the roadmap)
- `expected_fields`: JSON string

```json
{
  "brand_name": "Old Tom Distillery",
  "class_type": "Kentucky Straight Bourbon Whiskey",
  "alcohol_content": "45% Alc./Vol.",
  "net_contents": "750 mL",
  "bottler": "Old Tom Co., Frankfort, KY",
  "country_of_origin": null,
  "warning": null
}
```

`warning` is optional; when null the validator uses the standard TTB statutory text.

**Response:** `200 OK`

```json
{
  "review_id": "rev_2026...",
  "summary": {
    "status": "Needs Review",
    "headline": "5 of 7 fields match. 1 needs review and 1 mismatch on the Government Warning."
  },
  "extracted_fields": { "...": "..." },
  "field_comparisons": [
    {
      "field": "brand_name",
      "expected": "Old Tom Distillery",
      "found_raw": "OLD TOM DISTILLERY",
      "found_normalized": "old tom distillery",
      "status": "Match",
      "reason": "Case-only difference; normalized exact match.",
      "confidence": "high",
      "evidence_bbox": [120, 88, 540, 144]
    }
  ],
  "warning_validation": {
    "status": "Mismatch",
    "header_caps_ok": false,
    "wording_match": true,
    "raw_text": "Government Warning: ...",
    "reason": "Header 'Government Warning' is not in all caps.",
    "evidence_bbox": [80, 1120, 720, 1280]
  },
  "processing": {
    "elapsed_ms": 3420,
    "image_quality": "good",
    "stages_ms": { "preprocess": 280, "ocr": 2640, "compare": 90, "...": 0 },
    "ocr_provider": "paddleocr",
    "version": "0.1.0"
  },
  "limitations": [
    "This tool assists review and does not replace reviewer judgment."
  ]
}
```

**Errors:** structured JSON with `code`, `message`, and `recovery_hint`. File-too-large, unsupported-format, and unreadable-image have dedicated codes.

### `GET /api/v1/health`
Liveness/readiness check. Includes OCR-model-loaded flag.

### Sample data
- `GET /api/v1/samples/` — list synthetic + TTB reference samples.
- `GET /api/v1/samples/{id}/image` — fetch the image bytes for a single-label sample.
- `GET /api/v1/samples/{id}/expected-fields` — fetch the matching expected-fields JSON.
- `GET /api/v1/samples/batch`, `GET /api/v1/samples/batch/{id}/manifest`, `GET /api/v1/samples/batch/{id}/image/{filename}` — same idea for the seeded importer batch.

### Batch subsystem
- `POST /api/v1/batches` — create a batch from a CSV manifest plus N image files (multipart). Capped at 100 applications per batch.
- `GET /api/v1/batches`, `GET /api/v1/batches/{id}` — list batches and fetch one with its applications.
- `GET /api/v1/applications/{id}` — single-application detail (reuses the same response shape as `/reviews/analyze`).
- `GET /api/v1/applications/{id}/images/{image_id}` — fetch a stored application image.
- `PUT /api/v1/applications/{id}/decision` — record an analyst decision (approve / reject / needs correction / reset to pending) plus optional note.
- `POST /api/v1/batches/{id}/bulk-approve` — approve only the applications whose every field is `Match` at `high` confidence; returns approved + skipped counts with reasons.

All schemas are Pydantic models exported to OpenAPI at `/docs`.

## 6. Frontend architecture

- **Stack:** React 18 + Vite + TypeScript, Tailwind for styling with USWDS-aligned tokens.
- **Routing:** seven routes — `/` (home), `/review/new`, `/review/:id`, `/batches/new`, `/queue`, `/queue/applications/:id`, and a `*` not-found fallback.
- **State:** local component state plus React Query for the analyze call and the queue polling. No global store needed.
- **Feature folders:** `src/features/review/` owns the single-label upload, expected-fields form, processing screen, and results view; `src/features/batch/` owns importer submission; `src/features/queue/` owns the analyst queue and per-application detail. The `ResultsView` component is shared between the single-label flow and the queue detail page so the evidence-row UI stays identical.
- **Status display:** a single `<StatusChip>` component takes a status from the fixed vocabulary and renders text + icon + color, never color alone.
- **Accessibility:** full keyboard nav, visible focus rings, and status announcements via ARIA live regions on the processing and results screens. axe-core runs against the live DOM in development mode (wired in `src/main.tsx`) so violations surface in the browser console while iterating; there is no CI pipeline in this prototype, so axe-in-CI is on the roadmap rather than in place today.

## 7. Key decisions and the reasoning behind them

### Local OCR (PaddleOCR), not cloud
- Marcus's firewall constraint makes cloud OCR fragile.
- Latency from a remote call competes with our 5-second budget.
- A local provider is reproducible and inspectable in interview review.
- Trade-off: ~200MB of model weights in the container; cold start is slower. Mitigated by pre-downloading weights at image build time.

### No LLM in the decision path
- Deterministic comparison is easier to defend, faster, and reproducible.
- Adding an LLM on top of a deterministic core is straightforward later; removing one that has crept into the decision path is much harder.
- The "STONE'S THROW vs Stone's Throw" case is a solved problem with `rapidfuzz` plus Unicode normalization — sub-millisecond and inspectable.

### Tiered match status, not binary pass/fail
- Dave's testimony: real-world judgment is needed for benign differences.
- A `Needs Review` tier between `Match` and `Mismatch` lets the system acknowledge ambiguity instead of forcing a wrong answer.
- Every threshold is a constant in one file.

### Dedicated Government Warning validator
- Jenny's testimony: this is the field reviewers most often see abused.
- Mixing it into the generic comparison would let format violations slip through (e.g. correct wording with a title-case header).
- It runs independently and emits its own structured result.

### Single deployable container, monorepo
- Simplest reviewer experience: one URL, one set of logs.
- No queue, no multi-service orchestration — those would be overengineering for a prototype.

### Hugging Face Spaces for deployment
- CPU Basic tier: 16 GB RAM, 2 vCPU, free with no credit card required.
- Single Dockerfile; `sdk: docker` frontmatter in README triggers auto-build on push.
- PaddleOCR model weights (~200 MB) are baked in at build time, eliminating cold-start download delay.
- Render free tier is only 512 MB RAM, which OOMs PaddleOCR at load time.

## 8. What is explicitly out of scope

- COLA system integration.
- FedRAMP or any production compliance posture.
- Authentication and user management.
- Persistent storage of uploaded label images beyond the demo's needs.
- Multi-language OCR.
- Beverage-type-specific rule packs beyond the seven core fields.
- Mobile native app (the web UI is responsive but desktop-first).

## 9. Risks and mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| OCR misreads on stylized/decorative label fonts | High | Per-field confidence; `Needs Review` tier; raw evidence shown to reviewer |
| 5-second budget breached on large images | Medium | Resize during preprocess; surface elapsed time in UI; document bottleneck if it happens |
| PaddleOCR model size inflates Docker image | Medium | Pre-download at build time; document in trade-offs |
| Reviewer sees "Match" and assumes legal approval | Medium | UI never says "approved/rejected"; footer disclaimer; status vocabulary is comparison-only |
| Government Warning false negatives from OCR noise | Medium | Validator returns `Uncertain` instead of guessing; raw warning region shown for manual check |
| Demo deploy goes cold and first request times out | Low | Health check warms the OCR model; demo script notes the first-request lag |
