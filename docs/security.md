# Security review

This document is a prototype-scoped security audit of the AI-Powered Alcohol
Label Verification app. It records what was reviewed, what is in good shape,
what should be hardened before reviewers exercise the deployed URL, and what
is intentionally deferred as out-of-scope for a take-home.

It is written for an interview reviewer who wants to see the engineering
judgment behind the security posture, not just a checklist.

The bar is "production-minded prototype, not production-complete." Where a
real regulated workflow would require more (auth, audit logging, FedRAMP
controls, formal threat model), that gap is documented in
[Regulatory posture](#regulatory-posture) rather than papered over.

## Scope

In scope for this review:

- The public HTTP surface:
  - `POST /api/v1/reviews/analyze`
  - `GET  /api/v1/samples/*`
  - `GET  /api/v1/health`
  - The batch subsystem under `/api/v1/`:
    - `POST /batches`, `GET /batches`, `GET /batches/{id}`
    - `GET /applications/{id}`, `GET /applications/{id}/images/{image_id}`
    - `PUT /applications/{id}/decision`
    - `POST /batches/{id}/bulk-approve`
  - The SPA catch-all.
- Upload handling (validation, decoding, in-memory processing for
  `/analyze`; multipart manifest + N-image upload for `/batches`).
- Configuration and secret handling.
- Static file serving and deployment image (`Dockerfile`).
- Direct dependencies and their CVE posture.
- Data handling, including the AGENTS.md "raw OCR text is evidence" rule.
- Application-level logging (what is and isn't written to logs).
- Frontend XSS / client-side trust surface.

Note on persistence: the batch subsystem persists uploaded image bytes to
disk at `/tmp/alv_batch_uploads/<submission_id>/<filename>` and importer
metadata (name, email, optional note) plus per-application status to a
SQLite database at `/tmp/alv_batches.db`. Both locations are configurable
via `ALV_BATCH_STORAGE_DIR` and `ALV_BATCH_DB_PATH`. Both are ephemeral on
Hugging Face Spaces (the container's `/tmp` is wiped on restart) — see
[Data handling](#data-handling-and-the-agentsmd-raw-text-rule) for what
this means in practice. The `/analyze` endpoint remains fully in-memory
and writes nothing to disk.

Explicitly out of scope:

- Authentication and authorisation (intentionally absent for a prototype).
- Long-term retention, defensible deletion, encryption-at-rest.
- TTB / FedRAMP / SOC 2 / GDPR control mapping at depth.
- Formal threat modelling (STRIDE workshop, attack trees).
- Supply-chain attestation (SLSA, SBOM signing).

## Threat model summary

Realistic threats for the deployed prototype:

| Threat | Likelihood | Impact | Where it lands |
|---|---|---|---|
| Malicious upload (decompression bomb, malformed image) | Medium | Memory exhaustion, single-instance DoS | `preprocess` stage |
| Spoofed `Content-Type` to bypass allowlist | Low–Medium | Pillow decodes unexpected format; mostly contained | `reviews.py` upload path |
| Resource exhaustion via concurrent uploads | Medium | Per-process serialisation already throttles OCR; HTTP workers can still pile up | `paddle_ocr.py` lock |
| Cross-origin script injection via deployed origin | Low | None observed (React escaping; no `dangerouslySetInnerHTML`) | Frontend |
| Sensitive content leakage via logs | Low | Application logs record IDs, counts, paths, and exception traces; never OCR text, upload bytes, or importer PII | `batches.py`, `processor.py` |
| Path traversal via sample IDs | Low | Mitigated: lookup by manifest match, not path concatenation | `samples.py` |
| Path traversal via batch image filenames | Low | Mitigated: filenames are stored under server-generated submission UUIDs and image rows are looked up by row ID, not by client-supplied name | `batches.py` |
| Compromised dependency | Medium | Standard supply-chain risk | `pyproject.toml`, `package.json` |

Threats deliberately set aside for prototype scope:

- Insider abuse, credential theft, replay attacks (no auth in v1).
- Long-term data retention concerns (storage is ephemeral; see
  [Data handling](#data-handling-and-the-agentsmd-raw-text-rule)).
- Tampered TTB references in `sample_data/` (committed in-repo, build-time controlled).

## Findings

Severity is calibrated for a take-home prototype, not a production regulated
service. "High" means worth fixing before the deployed URL is shared with
reviewers; "Medium" means worth a small commit if time permits; "Low" means
documented and acceptable.

### High

#### H1. Pillow decompression bomb is not bounded

**Where:** `backend/app/services/extraction/preprocess.py` line 68.

```python
pil_img = Image.open(io.BytesIO(image_bytes))
pil_img = ImageOps.exif_transpose(pil_img)
pil_img = pil_img.convert("RGB")
```

The 10 MB byte-size guard in `reviews.py` does **not** bound logical pixel
count. A maliciously-crafted ~100 KB PNG declaring dimensions of e.g.
50 000 × 50 000 will allocate ~10 GB on `convert("RGB")` before any sanity
check fires. Pillow ships a `MAX_IMAGE_PIXELS` default of ~89 megapixels
(89,478,485 pixels), but at the default config it emits a
`DecompressionBombWarning` rather than raising; it only raises a
`DecompressionBombError` at 2× that threshold (~178 megapixels). At the
prototype's default config the warning is the only signal.

**Why this matters here:** the deployment is a single-process container on
Hugging Face Spaces free tier. One bomb upload per cold start kills the
container. The same risk applies to every image in a `/batches` upload.

**Remediation:**

- Set `Image.MAX_IMAGE_PIXELS` to a reasonable cap (e.g. 25 megapixels —
  generously above any phone-quality label photo).
- Convert Pillow's `Image.DecompressionBombWarning` to an error, or call
  `pil_img.verify()` on a separate handle and reject on any exception.
- Reject upfront if `pil_img.size[0] * pil_img.size[1]` exceeds the cap,
  rather than allocating then catching.

Effort: ~10 lines, plus a unit test using a small declared-large PNG. The
fix lives in `preprocess.py` and applies to both `/analyze` and `/batches`
because both flows funnel through the same preprocess stage.

### Medium

#### M1. `Content-Type` is trusted without magic-byte verification

**Where:** `backend/app/api/reviews.py` lines 51–62.

```python
if image.content_type not in settings.allowed_image_types:
    raise HTTPException(...)
```

`UploadFile.content_type` is the value the client put in the multipart
header. A malicious client can claim `image/png` for any payload. Pillow's
own decoder catches malformed bytes and the request fails with
`unreadable_image`, so the practical risk is bounded — but the allowlist is
not enforcing what it claims to enforce.

**Remediation:**

- After reading `body`, verify the magic bytes (PNG: `89 50 4E 47`, JPEG:
  `FF D8 FF`) match the declared type before passing to `preprocess`.
- Or, accept the soft-failure approach and rename the error code so the API
  doesn't claim to "validate" type strictly.

Effort: ~6 lines.

#### M2. No HTTP security headers on responses

**Where:** `backend/app/main.py`. `CORSMiddleware` is the only middleware.

The deployed app serves a SPA + API from the same origin. There are no
response headers for:

- `Content-Security-Policy` (defence in depth against XSS, even with React).
- `X-Content-Type-Options: nosniff`.
- `X-Frame-Options` / `frame-ancestors` (clickjacking).
- `Referrer-Policy`.
- `Permissions-Policy`.

The unauthenticated POST/PUT surface has grown beyond `/analyze` to include
`POST /batches`, `PUT /applications/{id}/decision`, and
`POST /batches/{id}/bulk-approve`. CSRF is still bounded because
`allow_credentials=False` (no cookies are honoured cross-origin), but a
header-stripped browser environment is a thinner defence against future
mistakes than headers + same-origin policy together.

**Remediation:**

- Add a small middleware that sets a conservative header set on every
  response. CSP can be `default-src 'self'; img-src 'self' data: blob:;
  style-src 'self' 'unsafe-inline'` — tightening `style-src` later if the
  Tailwind build allows.

Effort: one new file (~30 lines) and a header-presence test.

#### M3. No rate limiting on the analyze or batch endpoints

`POST /api/v1/reviews/analyze` is unauthenticated and CPU-bound (1–3 s
under PaddleOCR). The `_ocr_lock` in `paddle_ocr.py` already serialises
inference, which means an attacker with a small client pool can hold the
queue indefinitely. `POST /api/v1/batches` amplifies this — a single
request can enqueue dozens of OCR jobs against the same lock.

**Remediation for the prototype:** document the limit and accept the risk
for the take-home; the deployed URL is shared with a small audience. If a
real defence is wanted, `slowapi` or `fastapi-limiter` adds per-IP limits in
~20 lines without external infra.

#### M4. `expected_fields` JSON has no explicit size cap

**Where:** `backend/app/api/reviews.py` line 92.

```python
expected_payload = json.loads(expected_fields) if expected_fields else {}
```

Starlette's multipart parser has implicit upper bounds, but they are
permissive. A multi-MB JSON string would parse and then be rejected by
Pydantic's `extra="forbid"`, which is wasted CPU. The same concern applies
to the batch `meta` form field in `POST /batches`, which is parsed into
`BatchSubmissionMeta` via the same `json.loads` → Pydantic path.

**Remediation:** check `len(expected_fields)` (and `len(meta)` in
`batches.py`) against a small limit (e.g. 64 KB) before `json.loads`.
Effort: ~3 lines per call site.

### Low

#### L1. CORS `allow_headers=["*"]`

`allow_credentials=False` mitigates the classic risk; the wildcard is
acceptable for a prototype with no cookies. Could tighten to
`["Content-Type"]`. Documented and accepted.

#### L2. Error responses echo client-supplied `Content-Type`

```python
message=f"File type {image.content_type!r} is not supported."
```

`repr()` quotes and escapes, so this isn't a reflected-XSS vector through
the JSON API, but it is reflected user input. Worth truncating to e.g. 64
characters to bound surface area.

#### L3. Application-level logging — review of what is recorded

Application-level logging exists in two places:

- `backend/app/api/batches.py`: one `logger.info` on batch creation
  (logs `batch_id`, application count, image count, total KiB) and one
  `logger.warning` when an image row points to a missing file on disk
  (logs `image_id`, `application_id`, stored path).
- `backend/app/services/batch/processor.py`: four entries —
  `logger.warning` when an application id is missing from the store, and
  three `logger.exception` calls when a stored image cannot be read or
  the analysis pipeline fails (each logs the application id and an
  exception trace from the underlying service).

What is **not** logged today:

- OCR text, normalised text, or any `OcrToken` content.
- Uploaded image bytes or filenames as supplied by the client (only the
  server-generated stored path appears).
- Importer name, email, or note from the batch metadata.
- Pydantic validation input (the validation error path extracts `loc`
  only, never the offending value — see "Positive findings" below).

The `/analyze` endpoint emits no application-level log lines today; the
only record of a single-image request is the uvicorn access log.

**Recommendation if the prototype graduates:** formalise the current
posture as policy ("never log OCR text, raw upload bytes, or importer
PII; IDs and counts only") and enforce it with a structured logging
formatter (`structlog` or stdlib `logging` JSON formatter) plus a
per-request correlation ID. Keep it for a future iteration.

#### L4. Manifest paths joined to `samples_dir` without containment check

**Where:** `backend/app/api/samples.py` lines 151 and 173.

```python
image_path = Path(settings.samples_dir) / entry.image_path
fields_path = Path(settings.samples_dir) / entry.expected_fields_path
```

The manifest is committed in-repo and build-time controlled, so this is
not a current vulnerability. The user-input branch (`/samples/{id}/image/
{filename}`) already enforces containment — see `_safe_image_path` at
`samples.py:235`, which strips path separators and rejects mismatches
before joining. The remaining concern is manifest-controlled paths only:
defence in depth would resolve the joined path and verify it is
contained within `Path(settings.samples_dir).resolve()` before serving.
Effort: 4 lines. Worth doing if the manifest ever becomes runtime-loaded.

#### L5. Frontend dev toolchain CVEs

Already documented in `tradeoffs.md` ("Frontend npm audit findings"):
`esbuild`/`vite` CVEs affect only `vite dev`, not the production static
bundle served by FastAPI. No production exposure. Tracked.

## Positive findings (worth keeping)

These are existing controls the audit verified are in place. Calling them
out here so reviewers know what was checked and what's already correct.

- **Upload size cap** enforced server-side at 10 MB
  (`reviews.py` lines 65–78), independent of the matching client-side check
  in `UploadSection.tsx`.
- **Empty-file rejection** with a structured error envelope.
- **Pydantic request schemas use `extra="forbid"`** on every public input
  model (`ExpectedFields`, `BatchSubmissionMeta`, `WorkflowDecision`,
  `BulkApproveRequest`), so unexpected fields are rejected rather than
  silently absorbed. Response-side schemas (`AnalyzeResponse`,
  `FieldComparison`, `Application`, `Batch`, etc.) use `frozen=True` only
  — the server controls their construction so `extra="forbid"` would not
  add value there.
- **Validation errors do not echo user input.** `reviews.py` lines 110–116
  deliberately extract `loc` paths only and skip `errors()[i]["input"]`.
- **CORS is restrictive for a public API.** Methods limited to
  `GET, POST, PUT, OPTIONS` (PUT is required for
  `/applications/{id}/decision`); `allow_credentials=False`; origin
  allowlist via env var rather than `*`.
- **Static + API mount order is correct.** API routers register before the
  SPA catch-all, so `/api/v1/*` cannot be shadowed by a static route.
- **SPA catch-all does not resolve user paths against the static directory.**
  The handler returns `index.html` unconditionally, sidestepping path
  traversal entirely (called out in a comment at `main.py` lines 82–90).
- **Batch image lookup is by row ID, not client filename.** Client-supplied
  filenames are stored as metadata; the actual disk path is constructed
  from a server-generated submission UUID and the canonical filename
  field on the image row. The `GET /applications/{id}/images/{image_id}`
  handler checks `path.is_file()` and 404s on miss rather than echoing
  the path back.
- **Container runs as non-root.** Dockerfile creates UID 1000 and `USER user`
  before any application paths are written.
- **Multi-stage Docker build.** No frontend tooling, npm cache, or Python
  build artifacts in the runtime image.
- **`.env` and OCR model cache are gitignored.** `.git` is dockerignored.
  No secrets material has been committed.
- **No `os.system`, `subprocess(shell=True)`, `eval`, `exec`, or template
  string code execution** anywhere in the backend.
- **No `dangerouslySetInnerHTML`, `innerHTML`, `eval()`, or `new Function()`**
  anywhere in the frontend. React's default escaping is the only render
  path for user-controlled strings (`file.name`, OCR text, error messages).
- **AbortController on the analyze request.** The Cancel button actually
  stops the request rather than hiding the spinner — confirmed in
  `client.ts`.
- **AGENTS.md "raw OCR text is evidence" rule is honoured.** OCR providers
  emit raw token text and downstream stages operate on copies; no mutation
  of `OcrToken.text` was found in the code path.
- **Dependency versions are recent.** `Pillow>=10.4.0` (post the 2024 CVE
  fixes), `python-multipart>=0.0.9` (post-CVE-2024-24762), pinned numpy
  major version.

## Configuration & secrets posture

- All runtime settings come from environment variables prefixed `ALV_*`,
  loaded by `pydantic-settings` from process env or a `.env` file.
- The repo contains no committed secrets (verified by inspection of
  `.gitignore`, `frontend/.env.example`, and a history search; there is no
  committed `backend/.env.example`, only a documented set of `ALV_*` keys
  in `settings.py`).
- `frontend/.env.example` contains only a non-sensitive base URL.
- The Dockerfile sets `ALV_OCR_PROVIDER`, `ALV_SAMPLES_DIR`, and
  `ALV_STATIC_DIR` to in-container paths only; no secret material is baked
  into the image.
- `cors_origins` is overridable at runtime via `ALV_CORS_ORIGINS` JSON.
- `ALV_BATCH_DB_PATH` and `ALV_BATCH_STORAGE_DIR` default to `/tmp/...` on
  the container; both can be repointed to a persistent volume if a
  deployment needs survival across restarts (the prototype does not).
- The PaddleOCR pre-download in the Docker build is a privacy plus:
  inference is fully local, so uploaded label bytes never leave the
  container.

## Data handling and the AGENTS.md raw-text rule

AGENTS.md explicitly forbids mutating, "cleaning up," or grammar-correcting
raw OCR text before comparison. The audit verified:

- `OcrToken.text` is set once from the provider and never reassigned.
- Normalisation in `services/validation/normalizers.py` operates on copies
  and emits both `raw_text` and `normalized_text` in the response.
- The frontend renders `found_raw` as the evidence panel and
  `found_normalized` separately when they differ.

**`/analyze` flow.** The image bytes never leave the request scope: they
are read into memory via `await image.read()`, passed through
`preprocess` and the OCR provider, and then dropped when the handler
returns. Nothing is written to disk. This is documented to the user in
the upload UI ("The image stays on the server only for the duration of
this review.") and is consistent with the implementation.

**`/batches` flow.** The batch endpoint persists differently because the
analyst queue must survive a page refresh:

- Uploaded image bytes are written to
  `<batch_storage_dir>/<submission_uuid>/<filename>` and read back by the
  background processor and the image-fetch endpoint.
- Importer metadata (name, email, optional note up to 2000 chars) and
  per-application status are written to a SQLite DB at `batch_db_path`.
- Both locations default to `/tmp/...` on Hugging Face Spaces, which is
  wiped on container restart. Retention for the prototype is therefore
  "until restart"; there is no scheduled deletion or rotation.
- No external service receives any of this data — OCR is local, the DB is
  local, and the image files are local.
- AGENTS.md's raw-text rule is honoured by the batch path the same way as
  `/analyze`: tokens flow through the same preprocess + OCR + comparison
  pipeline, and `OcrToken.text` is never mutated.

If a future iteration needs durable retention, the cleanest move is to
point `ALV_BATCH_DB_PATH` and `ALV_BATCH_STORAGE_DIR` at a persistent
volume and add a documented retention window with a sweep job. None of
that is in scope for the take-home.

## Regulatory posture

If this prototype graduated to a regulated workflow (TTB-adjacent
review, federal deployment, real submission data), the gap from "good
prototype" to "fit-for-purpose" includes:

| Area | Prototype state | Production-grade requirement |
|---|---|---|
| Authentication | None | Agency SSO / PIV / FIDO2; session management |
| Authorisation | None | Role-based: reviewer, supervisor, admin |
| Audit logging | App logs record IDs, counts, and exception traces only | Immutable per-action audit trail with actor, timestamp, decision, and field-status snapshot |
| Data retention | Ephemeral `/tmp` (container restart) | Documented retention schedule, encrypted-at-rest, defensible deletion |
| Network posture | HF Spaces public | Inside agency boundary; egress controls; FIPS-validated TLS |
| Dependency attestation | `pyproject.toml` versions | SBOM, signed builds, pinned hashes, vulnerability gating in CI |
| OCR provenance | Local model, version pinned | Plus reproducible model artefacts and an inference-quality regression suite |
| Threat model | This document | Formal STRIDE / attack-tree workshop with stakeholders |
| Privacy review | Importer name/email/note collected, ephemeral storage, never logged | DPIA / SORN coverage; minimisation review; documented lawful basis |
| Supply chain | Standard PyPI/npm | Internal mirrors; package signing; reviewed dep updates |

Note on workflow vocabulary: the codebase uses `approved` / `rejected` /
`needs_correction` / `pending_review` as `WorkflowStatus` enum values
because the analyst queue needs durable per-application state, and it
exposes a `bulk-approve` endpoint for clean Match-only applications. This
is a deliberate departure from the AGENTS.md "no approve/reject vocabulary"
rule and is documented in `docs/tradeoffs.md` ("Bulk-approve clean matches"
and the workflow-status section). For security-review purposes the
relevant fact is that the bulk-approve action records the field-status
snapshot at the moment of approval (see `batches.py` and the constants
comment), so an audit can reconstruct what was approved on what evidence.

None of the production-grade column is scoped for the take-home. The
point of listing it is to make the gap legible rather than implied.

## Recommended hardening sequence

If the next iteration spends a few hours on security hardening before the
deployed URL is shared with a wider audience, the highest-value sequence is:

1. **H1**: Pillow decompression bomb cap. ~10 lines + test, applies to
   both `/analyze` and `/batches`. (Worth doing.)
2. **M2**: Security headers middleware. ~30 lines + test. (Worth doing.)
3. **M1**: Magic-byte content type verification. ~6 lines + test.
4. **M4**: Bound `expected_fields` and batch `meta` JSON length. ~3 lines per call site.
5. **L4**: Resolve and contain manifest paths. ~4 lines.

The remaining items are documented gaps acceptable for prototype scope.

## How this was reviewed

- Read of every file under `backend/app/` and the relevant frontend files
  (`UploadSection.tsx`, `ResultsView.tsx`, `client.ts`, `index.html`,
  `package.json`).
- Search for dangerous primitives across the codebase
  (`eval`, `exec`, `os.system`, `shell=True`, `dangerouslySetInnerHTML`,
  `innerHTML`, raw HTML rendering, write operations).
- Inspection of `Dockerfile`, `.dockerignore`, `.gitignore`, and
  `pyproject.toml` for image hygiene and dependency posture.
- Inventory of every `logger.*` call site in the backend and a check of
  what each one passes as arguments.
- Cross-check against the operational notes already documented in
  `docs/tradeoffs.md` to avoid contradicting prior decisions.

No automated scanners were run for this audit; their output is not
particularly informative on a codebase this small. If `pip-audit`,
`bandit`, or `npm audit` runs are wanted as a CI gate, they should be added
deliberately rather than retroactively from a one-shot scan.
