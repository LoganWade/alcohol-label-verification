# Demo script

A short walkthrough for an interview reviewer evaluating the deployed app. Estimated time: 5 minutes.

## Before you start

- Open the deployed URL (recorded at the top of the README once deployed).
- The first request may take 5–10 seconds while the OCR model warms up. Subsequent requests should be in the 3–4 second range on typical labels.

## 1. The clean happy path (~60 seconds)

1. From the home screen, click **Try with sample data**.
2. Choose the **"Old Tom Distillery — clean match"** scenario.
3. Click **Run review**.
4. Observe the processing screen: progress indicator within ~200ms, named pipeline stages, elapsed timer.
5. On the results screen, all seven fields should show `Match` and the Government Warning should show `Match` with a `header_caps_ok: true` indicator.
6. Click any field row to expand its evidence panel: cropped region of the original image, raw OCR text, and the rule that decided the outcome.

**What to look for:** the round-trip elapsed time at the top of the results page; field-level evidence; the disclaimer footer that says the tool assists review and does not replace reviewer judgment.

## 2. The "Stone's Throw" case (~45 seconds)

1. Return to the home screen, click **Try with sample data** again.
2. Choose **"Stone's Throw — case mismatch"**.
3. Run the review.

The brand-name comparison should resolve to `Match` with a "normalized exact match (case-insensitive)" reason. This is Dave Morrison's central concern: a benign formatting difference is recognized as the same value.

## 3. The Government Warning trap (~60 seconds)

1. Choose **"Old Tom — title-case warning header"**.
2. Run the review.

The warning row will read `Mismatch` with the explanation that the literal `GOVERNMENT WARNING` header is not in all caps, even though the body of the warning is correct. This is Jenny Park's strict-header rule, enforced by the dedicated warning validator rather than the generic comparator.

Click the warning row to see the cropped region of the warning area on the label and the raw OCR text. The same row also shows `wording_match: true` so a reviewer can see *exactly* what failed.

## 4. The unreadable image (~45 seconds)

1. Choose **"Skewed and dark photo"**.
2. Run the review.

Several fields will resolve to `Needs Review` or `Uncertain` rather than guessing. The processing metadata reports an image-quality tier of `poor`, and the limitations array explicitly notes that confidence propagated from the preprocess stage.

## 5. Optional: keyboard-only walkthrough

Tab through the entire flow without using the mouse. Every interactive control should be reachable, every focus state visible, and every status announcement readable by a screen reader (test with VoiceOver on macOS or NVDA on Windows). This satisfies the WCAG 2.2 AA bar set in `AGENTS.md`.

## 6. Batch upload (importer + analyst flow, ~3 minutes)

The single-image flow above is the reviewer-on-the-spot tool. The batch flow addresses Janet Goodwin's quote from the discovery interviews:

> "During peak season, we get these big importers who dump 200, 300 label applications on us at once... If there was some way to handle batch uploads, that would be huge."

The demo flow runs both roles end-to-end on a small sample batch.

### 6a. Importer side — submit a batch

1. From the home screen, click **Submit a batch**.
2. Fill in importer name and email (any plain-text values — Phase A intentionally has no auth).
3. Pick a manifest CSV. The expected columns are:
   `serial_number, brand_name, fanciful_name, class_type, alcohol_content, net_contents, bottler, country_of_origin, image_filename, attribution, is_primary`.
4. Pick the matching image files (one row per primary image; `is_primary=true` exactly once per `serial_number`).
5. Click **Submit batch**. On success the page redirects to the analyst queue with the new batch pre-selected.

**What to look for:** if the manifest is malformed, the page renders a row-by-row error table (row number, column, message) instead of a generic error — every problem is locatable in the source CSV.

### 6b. Analyst side — work the queue

1. The right pane shows the new batch with each application in `Queued` or `Processing` state. The page polls every 1.5 seconds while any application is still in flight, then stops on its own once everything is `Analyzed`.
2. Click **Bulk-approve clean matches**. Only applications where every field comparison resolves to `Match` *and* every confidence is `high` are approved; everything else is skipped, and the response shows the counts plus reasons.
3. For an application that wasn't bulk-approved, click **Open** to drill into the per-application detail page.
4. The detail page reuses the same `ResultsView` component as the single-image flow — same expandable rows, same cropped evidence, same status chips.
5. Set a workflow decision (Approve / Reject / Needs correction / Reset to pending) with an optional analyst note. The decision is persisted via `PUT /applications/{id}/decision` and the queue counts update on the next refresh.

**What to look for:** the verb "approved" only appears on the *workflow* layer — the underlying pipeline output still uses the `Match | Mismatch | Missing | Needs Review | Uncertain` vocabulary. Workflow status and pipeline status are separate fields by design (see `docs/tradeoffs.md`).

### 6c. Constraints worth pointing out

- **100 application cap per batch.** Janet's 200–300 number is explicitly out of scope for Phase A; the cap is enforced by the manifest parser and is a roadmap item, not a silent limit.
- **One primary image per application.** Phase A only OCRs the primary image. Back/neck/body images are stored but not analyzed yet.
- **Storage is `/tmp`-backed SQLite.** Resilient enough for a demo, intentionally not for production. The full set of trade-offs is documented in `docs/tradeoffs.md` under "Batch upload".

## What this demo deliberately does *not* do

- It never says "approved" or "rejected." Final compliance decisions are the reviewer's.
- It does not store uploaded images beyond the demo session.
- It does not call any external service. All processing is local to the deployment.
