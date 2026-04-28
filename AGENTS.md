---
name: alcohol_label_verification_sdlc_agent
version: 1
purpose: SDLC operating instructions for building and shipping the take-home AI-Powered Alcohol Label Verification App prototype.
---

# AGENTS.md

This file is the operating manual for coding agents working on the **AI-Powered Alcohol Label Verification App** take-home project. It defines scope, architecture expectations, delivery standards, commands, boundaries, and role-specific execution guidance so work stays production-minded while still fitting a time-boxed interview assignment.

## Product goal

Build a standalone prototype that helps compliance reviewers verify whether information on an alcohol label matches expected application data and whether required label content is present. The prototype should prioritize speed, clarity, and reviewer trust over breadth of features.

## Project context

The assignment is a take-home project for an interview process. The reviewers want to assess engineering decisions, design judgment, code quality, UX, and the ability to make reasonable trade-offs under time constraints.

The application context and constraints inferred from the assignment:
- Users are compliance agents with mixed technical comfort.
- Core workflow is visual comparison between uploaded label images and structured expected fields.
- A useful prototype should return results in roughly 5 seconds or less for a single-label check when feasible.
- Batch upload is a desirable stretch feature.
- This is a standalone proof-of-concept, not a direct integration with the legacy COLA system.
- Outbound-network assumptions may be unreliable in government environments, so designs should minimize dependency on fragile remote services.
- A working core app with clean code is preferred over ambitious but incomplete features.

## Success criteria

The finished repo and deployed app should optimize for the following:
- End-to-end working prototype.
- Clear README with setup, run, architecture, trade-offs, and demo instructions.
- Strong UX for non-technical reviewers.
- Reliable extraction/comparison pipeline for the core required fields.
- Good error handling and visible confidence/limitations.
- Clean, testable, production-style code organization.
- Sensible documentation of assumptions and future improvements.

## Recommended implementation stance

Default to a pragmatic full-stack Python architecture:
- **Backend:** FastAPI.
- **Frontend:** React with Vite, or Next.js only if speed of delivery remains high.
- **OCR / document intelligence:** Prefer a local-first or pluggable abstraction. Tesseract, PaddleOCR, or a provider adapter are acceptable. Do not hard-couple the app to a paid external API.
- **Image handling:** Pillow / OpenCV for preprocessing.
- **Validation logic:** deterministic Python rules first, AI-assisted interpretation second.
- **Persistence:** lightweight SQLite for prototype metadata if needed; otherwise keep state ephemeral.
- **Deployment:** one-click deploy target such as Render, Railway, Fly.io, or Azure Static Web Apps + backend service.

Reasoning for agents: deterministic checks build reviewer trust. Use LLMs only where they add clear value, such as extracting noisy text or generating a human-readable discrepancy summary. The core compliance checks must remain inspectable.

## User-facing scope

### Core features
- Upload a label image.
- Enter or load expected application fields.
- Extract label text and key entities from the image.
- Compare extracted values against expected values.
- Verify the required government warning statement.
- Show a reviewer-friendly result summary: pass, mismatch, missing, uncertain.
- Display extracted evidence with field-level confidence where possible.
- Handle common failure states cleanly.

### Important fields
Treat the following as first-class fields in the initial prototype:
- Brand name.
- Class/type designation.
- Alcohol content / ABV / proof where applicable.
- Net contents.
- Bottler / producer name and address.
- Country of origin for imports when supplied in test data.
- Government Health Warning Statement.

### Stretch features
Only pursue these after the core workflow is working:
- Batch upload and queue processing.
- Skew / glare / perspective correction.
- Review history.
- Saved sample labels and seeded demo mode.
- Side-by-side diff visualization.

## Non-goals
- Direct integration with COLA or federal internal systems.
- Full production compliance, FedRAMP, or enterprise auth.
- Perfect legal interpretation across all beverage edge cases.
- Complex user roles or workflow orchestration.
- Overbuilt infrastructure for a take-home assignment.

## Extraction pipeline stages

Treat label processing as a sequence of named, independently testable stages. Each stage has an explicit input contract, an explicit output contract, and a confidence/quality report. Pipelines that hide stages behind a single "OCR" call are harder to debug, harder to test, and erode reviewer trust.

### Stages
1. **Preprocess** — quality assessment, deskew, perspective correction (stretch), contrast/binarization, resize. Emits a per-image quality report.
2. **OCR** — raw text extraction with bounding boxes and per-token confidence. Output is treated as immutable evidence from this point forward.
3. **Region attribution** — map OCR tokens to candidate label fields using spatial heuristics, regex anchors, and known label patterns. Emits per-field candidates with provenance.
4. **Field extraction** — deterministic parsers for structured fields (ABV, proof, net contents) and best-candidate selection for free-text fields (brand, class, bottler).
5. **Comparison** — normalize expected and extracted values, run the tiered match logic, return status + reasoning.
6. **Warning validation** — dedicated validator for the Government Warning, run independently of the generic comparison stage.
7. **Reporting** — aggregate stage outputs into the API response: extracted fields, comparisons, warning result, summary, processing metadata, limitations.

### Stage rules
- Each stage lives in its own module under `services/extraction/` or `services/validation/` and exposes a typed function with Pydantic input and output models.
- Each stage produces a confidence or quality indicator the next stage can consume.
- Each stage is independently unit-testable with fixtures.
- **The raw OCR string is evidence and must never be mutated before comparison.** Normalization is applied to *copies* used for matching only; the original extracted text is preserved for the UI and the API response.
- Uncertainty propagates forward. If preprocessing flags poor image quality, downstream stages must reflect that in their confidence outputs rather than asserting false certainty.
- When a stage cannot produce a result, it returns an explicit `uncertain` state with a reason — never a guess.

## Architecture principles

1. Build for **clarity first**.
2. Keep extraction and compliance rules separate.
3. Make every comparison traceable to evidence.
4. Prefer deterministic rules over agentic behavior in validation.
5. Keep external dependencies minimal and replaceable.
6. Design for graceful degradation when OCR quality is poor.
7. Expose limitations rather than hiding uncertainty.

## Suggested repository layout

Use this layout unless there is a strong reason to simplify:

```text
.
├── AGENTS.md
├── README.md
├── docs/
│   ├── architecture.md
│   ├── tradeoffs.md
│   ├── test-data.md
│   └── demo-script.md
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   ├── components/
│   │   ├── features/review/
│   │   ├── lib/api/
│   │   ├── lib/types/
│   │   └── styles/
│   ├── public/
│   └── package.json
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── services/
│   │   │   ├── extraction/    # preprocess, ocr, region_attribution, field_extraction
│   │   │   ├── validation/    # comparison, warning_validator, normalizers
│   │   │   └── reporting/     # response aggregation
│   │   ├── utils/
│   │   └── main.py
│   ├── tests/
│   ├── pyproject.toml
│   └── requirements.txt
├── sample_data/
│   ├── labels/
│   └── expected_fields/
└── scripts/
```

For a tighter timebox, a monorepo with `frontend/` and `backend/` is preferred over a more complex workspace toolchain.

## Domain rules for v1

### Matching rules
- Use exact match after normalization for strongly structured values where possible.
- Use normalization before comparison: trim whitespace, collapse repeated spaces, normalize punctuation variants, standardize capitalization for tolerant fields.
- Distinguish **hard mismatch** from **possible match**.
- For brand names, allow case-insensitive normalized comparison, but preserve the original values in the UI.
- For the government warning, treat wording differences as failures unless an explicit near-match state is shown.

### Government warning handling
Agents must implement a dedicated validator for the warning statement.
- Check presence.
- Check full expected text.
- Optionally flag formatting heuristics such as all-caps “GOVERNMENT WARNING,” but do not claim formatting certainty if OCR confidence is weak.
- If the warning is partially visible or OCR is unreliable, return `uncertain` rather than false confidence.

### Confidence model
Use a simple explainable confidence model:
- `high`: exact or normalized exact match with solid OCR evidence.
- `medium`: likely match with minor OCR noise.
- `low`: partial evidence, ambiguous extraction, or poor image quality.
- `uncertain`: insufficient evidence to support a reviewer decision.

## UX foundations

This app will be evaluated by reviewers from a federal agency context and used by reviewers with mixed technical comfort and a wide age range. Ground all UX decisions in the following authoritative references rather than ad-hoc taste:

- **U.S. Web Design System (USWDS)** — federal design system. Adopt its color tokens, spacing scale, and component patterns (or a Tailwind subset that mirrors them) for federal-feeling polish without pulling the full library.
- **WCAG 2.2 AA** — minimum accessibility bar. Half the user team is over 50.
- **18F Plain Language guidelines** — reviewer-facing copy must be plain, calm, and unambiguous.
- **Nielsen Norman heuristics** — especially *visibility of system status*, *error prevention*, and *help users recognize, diagnose, and recover from errors*.

### Required standards
- Text contrast minimum 4.5:1 for body, 3:1 for large text and meaningful UI.
- Interactive targets at least 44×44px.
- Full keyboard navigation; visible focus rings preserved on all controls.
- Reading level: roughly 8th grade. No ML jargon, no internal acronyms.
- Fixed status vocabulary across UI and API: `Match`, `Mismatch`, `Missing`, `Needs Review`, `Uncertain`. No frontend-only synonyms.
- No color-only signals. Every status conveyed via three redundant channels: **text label + icon + color**.

### Divergence rule
Any divergence from USWDS-aligned tokens or WCAG 2.2 AA requires a note in `docs/tradeoffs.md` explaining the reason and the mitigation.

## UX rules

This app is for users with varied technical ability. The UI should feel obvious and calm.

### Always do
- Use plain language, not ML jargon.
- Present one main action per screen.
- Show upload, processing, and results in a linear flow.
- Use side-by-side “Expected” vs “Found” comparisons.
- Label statuses clearly: `Match`, `Mismatch`, `Missing`, `Needs Review`.
- Keep error messages actionable.
- Make loading states and processing time visible.
- Include a small note explaining that the tool assists review and does not replace reviewer judgment.

### Avoid
- Dense dashboards on the main screen.
- Hidden controls or unclear icons.
- Confidence scores without explanation.
- Raw OCR dumps as the primary interface.
- Overly colorful success/error palettes that make the app feel toy-like.

### Status communication
- Every status must be conveyed through **text label + icon + color** simultaneously. Never color alone.
- Error messages must answer three questions in plain language: **what happened**, **why** (in user terms, not stack traces), and **what to do next**.
- Loading states must show: a progress indicator within 200 ms, the current pipeline step (e.g. "Reading image", "Extracting text", "Comparing fields", "Checking warning"), and an elapsed-time counter.
- Long-running operations (>8s) must surface a calm explanatory message rather than going silent.
- Cancellation must be available and must actually stop work, not just hide the spinner.
- The app must never use the words "approved" or "rejected." Final decisions belong to the reviewer; the app reports comparison status only.

## API guidance

Preferred API shape:

### `POST /api/v1/reviews/analyze`
Input:
- image file
- expected fields JSON

Output:
- extracted fields
- field comparisons
- warning validation result
- overall summary
- processing metadata
- warnings / limitations

### `GET /api/v1/health`
Simple readiness check.

### Optional
- `POST /api/v1/reviews/batch`
- `GET /api/v1/reviews/{id}`

Agents should keep request/response schemas explicit with Pydantic models.

## Engineering workflow

Follow this sequence unless the user asks otherwise:

1. Read assignment and restate scope in `docs/architecture.md`.
2. Define the v1 user journey and success path.
3. Create backend schema models and API contracts first.
4. Implement extraction service abstraction with one working provider.
5. Implement deterministic validators and comparison rules.
6. Build a minimal but polished UI around the happy path.
7. Add seeded sample data and demo scenarios.
8. Add tests for normalization, validators, and key API flows.
9. Deploy only after local end-to-end flow works.
10. Update README and trade-offs documentation last.

## SDLC phase guidance

### 1. Discovery
Deliverables:
- Scope summary.
- Assumptions list.
- Risk register.
- Chosen architecture.

Questions to resolve early:
- Which OCR path is most reliable under time constraints?
- What is the minimal field set for a compelling demo?
- What image-quality problems will v1 support?
- Is batch mode in or out for the first milestone?

### 2. Design
Produce:
- Screen-level flow.
- API contract.
- Core domain model.
- Validation rule list.
- Error-state matrix.

### 3. Build
Prioritize:
- Review flow.
- Evidence extraction.
- Comparison rendering.
- Warning validation.
- Error handling.

### 4. Verify
Required verification:
- Unit tests for normalizers and validators.
- Integration test for analyze endpoint.
- Manual test with at least 5 sample labels.
- Smoke test on deployed app.

### 5. Release
Ship:
- Deployed URL.
- README.
- Architecture and trade-offs docs.
- Clear known limitations.

## Commands

Agents must prefer explicit reproducible commands. If the actual stack differs, update this section immediately.

### Backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
pytest
ruff check .
```

### Frontend
```bash
cd frontend
npm install
npm run dev
npm run build
npm run lint
```

### Full app
```bash
# run frontend and backend in separate terminals
```

## Testing expectations

### Must-have tests
- Text normalization utilities.
- Brand-name comparison logic.
- ABV/proof parsing logic.
- Warning statement validator.
- Analyze API happy path.
- Failure path for unreadable or unsupported images.

### Nice-to-have tests
- Batch processing.
- Image preprocessing helpers.
- UI regression tests for result states.

### Accessibility tests
- Automated `axe-core` run on each route as part of frontend CI; zero serious or critical violations before merge.
- Manual keyboard-only walkthrough of the full review flow, documented in `docs/demo-script.md`.
- Screen-reader smoke test on the results screen (the most information-dense view), with notes on any unclear announcements.
- Color-contrast verification on all status chips, buttons, and form fields against WCAG 2.2 AA.

### Test data rules
- Keep sample labels and expected metadata in `sample_data/`.
- Prefer legally safe synthetic labels or clearly public sample imagery.
- Include both easy and noisy examples.
- Document provenance of any external sample assets.

## Code quality rules

### Backend
- Use type hints everywhere.
- Keep route handlers thin.
- Put business logic in services, not controllers.
- Use Pydantic models for contracts.
- Raise structured HTTP errors with actionable messages.
- Isolate OCR provider code behind an interface.

### Frontend
- Use feature-based organization.
- Keep components small and composable.
- Separate presentation from API state handling.
- Reflect backend statuses faithfully; do not invent frontend-only meanings for validation results.
- Prefer accessible HTML and keyboard-friendly controls.

### Documentation
Every meaningful engineering choice should be easy for interview reviewers to inspect.
Create or update:
- `README.md`
- `docs/architecture.md`
- `docs/tradeoffs.md`
- `docs/demo-script.md`

## Performance targets

Prototype-level targets:
- Single upload analysis should typically complete in under 5 seconds on normal test images.
- UI should show immediate progress feedback within 200 ms of submission.
- Large-image preprocessing should avoid obvious browser freezing.

If these targets are not met, document the bottleneck and mitigation.

## Security and privacy rules

Even though this is a prototype, agents should behave as if the app may later evolve into a regulated workflow.

### Always do
- Keep secrets in environment variables.
- Sanitize filenames.
- Validate file types and size limits.
- Avoid logging sensitive uploaded content verbatim.
- Document retention assumptions.

### Ask first
- Adding third-party hosted AI services that require sending images to external APIs.
- Adding persistent storage of uploaded labels beyond demo needs.
- Adding authentication.

### Never do
- Commit secrets, tokens, or real credentials.
- Hardcode API keys.
- Claim the prototype is legally compliant for production use.
- State that the system fully automates regulatory review.

## Boundaries

Use the three-tier model consistently.

### ✅ Always do
- Keep scope aligned to the assignment.
- Prefer working core functionality over speculative extras.
- Preserve a clean repo structure.
- Record assumptions and trade-offs.
- Make uncertainty visible in the UI and API.
- Run tests and lint before major handoff points.

### ⚠️ Ask first
- Replacing the stack with a radically different one.
- Adding heavyweight infra, auth, queues, or databases.
- Building multi-step batch workflows before single-review flow is strong.
- Introducing autonomous agent loops or opaque orchestration.
- Editing generated sample data in a way that changes demo expectations.

### 🚫 Never do
- Skip the core government warning validation.
- Hide OCR uncertainty behind a binary pass/fail.
- Overengineer for enterprise scale.
- Break the app into microservices.
- Depend on a fragile paid API without a fallback plan.
- Remove failing tests instead of fixing root causes.
- Add fake claims about model accuracy.
- Mutate, "clean up," or grammar-correct raw OCR text before comparison. Raw extracted text is evidence. Apply normalization only to throwaway copies used for matching, and preserve the original verbatim in the UI and API response.

## Role-specific sub-agents

These can exist as nested files under `.github/agents/` or docs if the workflow supports multiple specialized agents.

### `product-agent`
Responsibilities:
- Clarify scope.
- Keep the build aligned to reviewer expectations.
- Maintain trade-offs and milestone cuts.

### `backend-agent`
Responsibilities:
- API design.
- OCR abstraction.
- Validation services.
- Tests.

Special rule:
- Ask before changing API contracts after frontend integration begins.

### `frontend-agent`
Responsibilities:
- Upload flow.
- Review UI.
- Result clarity.
- Accessibility.

Special rules:
- Do not bury reviewer evidence behind tabs unless it improves comprehension.
- Default to USWDS-aligned tokens and WCAG 2.2 AA. Any divergence requires a note in `docs/tradeoffs.md`.
- Use the fixed status vocabulary (`Match`, `Mismatch`, `Missing`, `Needs Review`, `Uncertain`) verbatim. Do not invent synonyms or frontend-only states.

### `qa-agent`
Responsibilities:
- Test plan.
- Edge-case matrix.
- Regression checks.
- Demo verification.

Special rule:
- Never delete tests just to make CI green.

### `docs-agent`
Responsibilities:
- README.
- Architecture notes.
- Trade-offs.
- Demo guide.

Special rule:
- Explain assumptions plainly and avoid marketing language.

### `deploy-agent`
Responsibilities:
- Packaging.
- Environment variable docs.
- Deployment configuration.
- Smoke checks.

Special rule:
- Deploy to a simple environment and optimize for reviewer access, not infrastructure sophistication.

## Definition of done

The project is done when all of the following are true:
- A reviewer can open the deployed app and complete a label verification flow.
- The app accepts a sample image and expected fields.
- The backend returns extracted fields, comparison results, and a warning check.
- The UI presents the decision in a reviewer-friendly way.
- README setup instructions work on a clean machine.
- Tests cover core validation logic.
- Known limitations are documented honestly.
- The solution feels production-minded without pretending to be production-complete.

## Reviewer optimization notes

Agents should optimize for interview readability:
- Choose boring, dependable technologies over clever ones.
- Leave the repo cleaner than you found it.
- Favor understandable code over abstraction-heavy patterns.
- Make trade-offs explicit.
- Use comments sparingly and only where domain rules are non-obvious.
- Assume reviewers will inspect architecture, tests, README, and deployed UX more closely than raw feature count.

## Change management

When making substantial changes, update in the same PR or commit set:
- README if setup or architecture changes.
- tests if behavior changes.
- docs/tradeoffs.md if a trade-off is introduced.
- API schema docs if request or response contracts change.

## Final handoff checklist

Before declaring completion, verify:
- App runs locally.
- Deployed URL works.
- Main path demo works with provided sample data.
- Lint passes.
- Tests pass.
- README is current.
- Known limitations are documented.
- Screenshots or demo notes are ready if the submission format benefits from them.

