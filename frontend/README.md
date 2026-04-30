# Frontend — Alcohol Label Verification

React 18 + Vite + TypeScript frontend for the reviewer-assist label verification prototype. Two reviewer flows (single-label review, batch import + analyst queue) wired against the FastAPI backend.

## Setup

```bash
cd frontend
npm install
cp .env.example .env   # optional — defaults are fine for local dev
npm run dev            # http://localhost:5173
```

The dev server expects the FastAPI backend on `http://localhost:8000`. Override the API base URL with the `VITE_API_BASE_URL` environment variable.

## Scripts

| Command | What it does |
| --- | --- |
| `npm run dev` | Vite dev server on port 5173 |
| `npm run build` | Production build to `dist/` |
| `npm run preview` | Serve the production build locally |
| `npm test` | Run Vitest once |
| `npm run test:watch` | Vitest in watch mode |
| `npm run lint` | ESLint over `src/` |
| `npm run typecheck` | `tsc --noEmit` |

## Environment variables

| Variable | Default | Description |
| --- | --- | --- |
| `VITE_API_BASE_URL` | `http://localhost:8000/api/v1` | Backend API base. Used by `src/lib/api/client.ts`. |

## Architecture

The app is a Vite + React 18 single-page application. It uses **React Router v6** (seven routes: `/`, `/review/new`, `/review/:id`, `/batches/new`, `/queue`, `/queue/applications/:id`, and a `*` not-found), **TanStack Query v5** for server state (`analyzeLabel`, `createBatch`, `setApplicationDecision`, `bulkApproveBatch`, plus the polling queries that drive the analyst queue), and **Tailwind CSS** with a custom config that mirrors USWDS color tokens (calm federal blue, neutral grays, muted status semantics) and an 8-pixel spacing scale — without pulling the full USWDS library (see `docs/tradeoffs.md` "React + Vite + TypeScript with a Tailwind subset"). All status display goes through one `<StatusChip>` component that renders **text + icon + color** simultaneously per AGENTS.md's accessibility rule. Feature folders under `src/features/` (`home`, `review`, `batch`, `queue`) hold their own pages and presentation components; the API contract lives in `src/lib/types/api.ts` and mirrors the backend Pydantic schemas verbatim. A persistent `<Sidebar>` shell with `<Breadcrumbs>` runs across every reviewer route. Accessibility is reinforced at runtime by `@axe-core/react` in dev mode (logs violations to the console), `aria-live` regions on the processing and results screens, proper label/input association, 44×44px minimum interactive targets, and visible focus rings.

### Source layout

```
src/
├── app/            # App shell (router + Layout)
├── components/     # Cross-feature primitives: Button, Field, StatusChip,
│                   #   Layout, Sidebar, Breadcrumbs, ErrorPanel
├── features/
│   ├── home/       # HomePage, NotFoundPage
│   ├── review/     # ReviewNewPage, ResultsPage, ResultsView, sections,
│   │               #   BoundingBoxPreview
│   ├── batch/      # BatchUploadPage (importer flow)
│   └── queue/      # QueuePage, ApplicationDetailPage (analyst flow)
├── lib/
│   ├── api/        # fetch client, batches, samples, AnalyzeApiError
│   ├── types/      # API contract types (mirror backend) + EMPTY_EXPECTED_FIELDS
│   └── sample.ts   # Stub-aligned sample data for the legacy ?sample=1 path
└── styles/         # Tailwind entry CSS
```

### Status vocabulary (binding)

The frontend uses these strings VERBATIM and never invents synonyms:

- Field status: `Match`, `Mismatch`, `Missing`, `Needs Review`, `Uncertain`
- Review summary status: `Pass`, `Mismatch`, `Needs Review`
- Application processing status: `pending`, `processing`, `complete`, `failed`
- Application workflow status: `pending_review`, `approved`, `rejected`, `needs_changes`

All five field statuses share the same `<StatusChip>` component, which carries text, an SVG icon (`aria-hidden="true"`), and a muted color class. Color is never the only signal.

### Reviewer flows

**Single-label review** (the original Phase-1/2 flow):

1. **Home** (`/`) — primary CTA "Start a label review", two secondary CTAs ("Submit a batch", "Open analyst queue"), and grouped sample cards (synthetic + TTB reference). Sample cards are `<Link>`s so middle-click and ⌘-click open in new tabs the way users expect.
2. **New review** (`/review/new`) — single page with progressively disclosed sections:
   - Expected fields form (Form / Paste JSON / Load sample tabs)
   - Upload (drag-and-drop + file picker, preview, 10 MB / PNG-JPG guard)
   - Processing (above-the-fold; cycling stages, elapsed counter, 8-second long-running message, working Cancel via `AbortController`)
3. **Results** (`/review/:id`) — large status chip + headline + elapsed time, then a field-by-field comparison table with `<BoundingBoxPreview>` crops on every row. The Government Warning has its own bottom row with `header_caps_ok` and `wording_match` sub-flags surfaced. Every row is expandable to show raw OCR text (verbatim), confidence, comparison reason, and bounding box coordinates. Footer offers Run another review, Export results (JSON), and Print.

**Batch import + analyst queue** (Phase 3):

1. **Submit a batch** (`/batches/new`) — importer-facing form: name + email + optional note, manifest CSV picker, multi-file image picker (with duplicate-filename detection that surfaces a "Skipped N duplicate files" notice). Submission errors come back as a per-row manifest error table.
2. **Analyst queue** (`/queue`) — list of all batches with per-status counts (pending / processing / complete / failed), polling until the queue settles. Selecting a batch opens its applications side panel.
3. **Application detail** (`/queue/applications/:id`) — full per-application view: extracted fields, comparison summary, decision controls (Approve / Reject / Needs changes). Bulk-approve clean matches at the batch level when every remaining application is high-confidence Match-only.

### Why a single page for the new-review flow?

Per AGENTS.md ("Show upload, processing, and results in a linear flow") the steps live on one page with progressive disclosure rather than separate routes. This keeps the user's prior input visible while they move forward and avoids navigation flicker. The processing section renders above the fold so reviewers see live progress on small viewports.

## Testing

`npm test` runs Vitest against jsdom. The suite covers:

- `<StatusChip>` rendering for all field and review statuses (text + icon present regardless of color).
- `<ExpectedFieldsForm>` Continue-button gating, sample loading, and warning toggle.
- `<ResultsView>` rendering of the summary, all five status chips, expandable evidence panels, and the Government Warning row across match / header-fail / wording-fail / missing / uncertain cases.
- `<ResultsPage>` route integration plus a narrow snapshot of the results region.
- `<ErrorPanel>` rendering of the `AnalyzeError` envelope (`message`, `recovery_hint`, `code`).
- `<HomePage>` sample-section rendering, batch-card placement, and loading skeleton.
- `<Sidebar>` and `<Breadcrumbs>` route-state behavior.
- `<BoundingBoxPreview>` natural-size loading, crop math, expand/collapse, and error states.
- `<UploadSection>` file-validation paths (wrong MIME, oversize, valid PNG, valid JPG).
- `<BatchUploadPage>` form rendering and importer field wiring.

88 tests across 13 files at the time of writing.

## Accessibility notes

- WCAG 2.2 AA targets: 4.5:1 contrast on body text, 3:1 on large text, 44×44px minimum interactive targets.
- Visible focus rings on every interactive element via `:focus-visible` in `src/styles/index.css`.
- Skip-to-main link in `<Layout>`.
- `aria-live="polite"` on the processing and results sections.
- `aria-current="page"` on active sidebar/breadcrumb links.
- `axe-core/react` runs in dev mode and logs violations.

## Out of scope (deferred)

- Persistent review history backed by SQLite (currently lives in React Router location state; hard refresh on `/review/:id` falls back to a "start a new review" prompt — see `docs/tradeoffs.md`).
- Real authentication / multi-tenant isolation.
- Automated axe-core run as part of CI (today axe-core is dev-only).
