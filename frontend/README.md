# Frontend — Alcohol Label Verification

React 18 + Vite + TypeScript frontend for the reviewer-assist label verification prototype. Three screens (home, new review, results) wired against the backend's `POST /api/v1/reviews/analyze` endpoint.

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

The app is a Vite + React 18 single-page application. It uses **React Router v6** for the three routes (`/`, `/review/new`, `/review/:id`), **TanStack Query v5** for the single `analyzeLabel` mutation, and **Tailwind CSS** with a custom config that mirrors USWDS color tokens (calm federal blue, neutral grays, muted status semantics) and an 8-pixel spacing scale — without pulling the full USWDS library (see `docs/tradeoffs.md` "React + Vite + TypeScript with a Tailwind subset"). All status display goes through one `<StatusChip>` component that renders **text + icon + color** simultaneously per AGENTS.md's accessibility rule. Feature folders under `src/features/` (`home`, `review`) hold their own pages and presentation components; the API contract lives in `src/lib/types/api.ts` and mirrors the backend Pydantic schemas verbatim. Accessibility is reinforced at runtime by `@axe-core/react` in dev mode (logs violations to the console), `aria-live` regions on the processing and results screens, proper label/input association, 44×44px minimum interactive targets, and visible focus rings.

### Source layout

```
src/
├── app/            # App shell (router-mounted)
├── components/     # Cross-feature primitives: Button, Field, StatusChip, Layout, ErrorPanel
├── features/
│   ├── home/       # HomePage, NotFoundPage
│   └── review/     # ReviewNewPage, ResultsPage, ResultsView, sections
├── lib/
│   ├── api/        # fetch client + AnalyzeApiError
│   ├── types/      # API contract types (mirror backend)
│   └── sample.ts   # Phase 2 stub-aligned sample data
└── styles/         # Tailwind entry CSS
```

### Status vocabulary (binding)

The frontend uses these strings VERBATIM and never invents synonyms:

- Field status: `Match`, `Mismatch`, `Missing`, `Needs Review`, `Uncertain`
- Review summary status: `Pass`, `Mismatch`, `Needs Review`

All five field statuses share the same `<StatusChip>` component, which carries text, an SVG icon (`aria-hidden="true"`), and a muted color class. Color is never the only signal.

### Reviewer flow

1. **Home** (`/`) — headline + two cards: "Start a label review" and "Try with sample data".
2. **New review** (`/review/new`) — single page, three progressively disclosed sections:
   - Expected fields form (Form / Paste JSON / Load sample tabs)
   - Upload (drag-and-drop + file picker, preview, 10 MB / PNG-JPG-PDF guard)
   - Processing (cycling stages, elapsed counter, 8-second long-running message, working Cancel via `AbortController`)
3. **Results** (`/review/:id`) — large status chip + headline + elapsed time, then a field-by-field comparison table. The Government Warning has its **own bottom row** with `header_caps_ok` and `wording_match` sub-flags surfaced. Every row is expandable to show raw OCR text (verbatim), confidence, comparison reason, and bounding box coordinates. Footer offers Run another review, Export results (JSON), and Print.

### Why a single page for the new-review flow?

Per AGENTS.md ("Show upload, processing, and results in a linear flow") the steps live on one page with progressive disclosure rather than separate routes. This keeps the user's prior input visible while they move forward and avoids navigation flicker.

## Testing

`npm test` runs Vitest against jsdom. The suite covers:

- `<StatusChip>` rendering for all field and review statuses (text + icon present regardless of color).
- `<ExpectedFieldsForm>` Continue-button gating, sample loading, and warning toggle.
- `<ResultsView>` rendering of the summary, all five status chips, expandable evidence panels, and the Government Warning row across match / header-fail / wording-fail / missing / uncertain cases.
- `<ResultsPage>` route integration plus a snapshot of the results region.
- `<ErrorPanel>` rendering of the AnalyzeError envelope (`message`, `recovery_hint`, `code`).

33 tests at the time of writing.

## Accessibility notes

- WCAG 2.2 AA targets: 4.5:1 contrast on body text, 3:1 on large text, 44×44px minimum interactive targets.
- Visible focus rings on every interactive element via `:focus-visible` in `src/styles/index.css`.
- Skip-to-main link in `<Layout>`.
- `aria-live="polite"` on the processing and results sections.
- `axe-core/react` runs in dev mode and logs violations.

## Out of scope (deferred)

- Batch upload and review history (Phase 3 stretch).
- Image crop preview in the evidence panel — currently shown as bounding box coordinates.
- Real seeded fixture set — Phase 2 ships one stub-aligned sample (`src/lib/sample.ts`).
