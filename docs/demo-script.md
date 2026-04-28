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

## What this demo deliberately does *not* do

- It never says "approved" or "rejected." Final compliance decisions are the reviewer's.
- It does not store uploaded images beyond the demo session.
- It does not call any external service. All processing is local to the deployment.
