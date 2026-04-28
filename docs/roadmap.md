# Roadmap

This document captures features identified during a review of the TTB labeling regulations for wine (27 CFR Part 4), malt beverages (27 CFR Part 7), and distilled spirits (27 CFR Part 5). The prototype scope intentionally covers the seven common fields well; this roadmap describes what it would take to make the app a credible production tool for TTB label review.

Items are grouped by theme and tiered as **Near-term** (high leverage, low architectural risk; would land first if the prototype evolves), **Mid-term** (require new subsystems), or **Longer-term** (require capabilities outside the current scope, such as physical-unit calibration or a vision-model upgrade).

## Near-term

### 1. Beverage-class rule packs

The current pipeline treats every label the same. The TTB regulations make it clear that wine, beer, and spirits are effectively three different products with three different field sets and three different validation logics. A rule-pack architecture would let the comparator branch on `beverage_class` and apply the right validators.

- **Wine pack (27 CFR Part 4)**: vintage rules (≥95% AVA, ≥85% other appellations), varietal threshold (75% one variety), Estate Bottled rules, sulfite declaration trigger (≥10 ppm), bottling-statement variants ("Bottled By" / "Produced and bottled by" / "Cellared and bottled by"), color-additive disclosures (Yellow #5, Carmine, Cochineal Extract).
- **Beer pack (27 CFR Part 7)**: strict ABV format `Alcohol __% by Volume` (reject "ABV" abbreviation), class/type expansion ("IPA" → must include "India Pale Ale"; styles like Hefeweizen require "Ale" or "Beer"), geographic-style qualifier rule ("Irish-Style" if not actually Irish), pints required in net contents (not just fl. oz.).
- **Spirits pack (27 CFR Part 5)**: standards of fill validator (allowed sizes: 1.8L, 1.75L, 1L, 900mL, 750mL, 720mL, 700mL, 375mL, 200mL, 100mL, 50mL; cans: 355/200/100/50mL), age-statement triggers (whisky <4 yr, certain brandies), neutral-spirits format (`____% Neutral Spirits Distilled from _____`), coloring/flavoring disclosure (caramel, certified color, artificial), the 12 standards of identity.

**Architectural impact**: additive. New `services/rules/{wine,beer,spirits}.py` modules behind a registry; comparator selects the pack based on a new `beverage_class` field on the review request. Disclosure-language requirements (#6 below) and net-contents unit normalization (#8 below) fold into these packs rather than living separately.

### 2. Conditional / triggered field validators

Many rules only fire when another field has a certain value. The current "expected fields" model is flat; these need a small rules engine.

- Vintage requires appellation (wine).
- Varietal requires appellation (wine).
- Sulfite declaration if ≥10 ppm (wine).
- Age statement required if whisky <4 years (spirits).
- "-Style" qualifier if geographic origin does not match (beer/spirits).
- Country of origin required if imported.

**Architectural impact**: a small `Rule` abstraction with `applies_to(extracted_fields) -> bool` and `validate(extracted_fields) -> ComparisonResult`. Lives inside the rule packs from #1.

### 3. Alcohol tolerance ranges (not exact match)

ABV is currently compared as a string. The regulations explicitly allow tolerances:
- Wine <14%: ±1.5%
- Wine ≥14%: ±1%
- Beer and spirits: their own tolerance bands.

ABV comparison should be a numeric tolerance check, not a fuzzy string match, and the status should explain *why* a 13.5% vs 14% delta is a `Match`.

**Architectural impact**: a new `AbvComparator` that lives alongside the existing string comparator. The pipeline routes the ABV field through it explicitly. Templated explanation strings get a numeric-tolerance variant.

### 7. Top-error early warnings

The TTB documents publish "most common rejection reasons" (appellation missing, class/type missing, varietal/vintage without appellation). The app could surface these as a **common pitfalls panel** on every review — even when a field passes, flag if it is the kind of thing TTB rejects most often.

**Architectural impact**: a static metadata layer on each rule pack ("this field is in the top-N rejection reasons"). The reporter renders the panel; no pipeline changes.

## Mid-term

### 4. Type size, contrast, and legibility checks

This is one of the top reviewer complaints in the project brief and appears across all three regulations (notably 27 CFR 7.53 and the TTB Beverage Alcohol Manual). It is a different class of check entirely; it needs the OCR bounding boxes and pixel measurements, not just text.

The TTB rules specify type size in points/millimeters and use plain language for contrast ("conspicuous and legible," "contrasting background"). Concretely:

- **Government Warning**: 2mm minimum type height for containers >237mL, 1mm for smaller.
- **Brand name, class/type, net contents, ABV**: minimum sizes that scale with container size (e.g., 2mm for containers ≤187mL, 3mm for larger).
- **Same field of vision** (spirits): brand + class/type + net contents must be visible from one viewing angle.

#### Proposed solution

A new pipeline stage, `legibility_check`, slotted between region attribution and field extraction. For each attributed field it would compute:

1. **Type size** — convert the bounding-box height in pixels to millimeters using a calibration factor:
   - **Easy path**: user enters container size on upload (e.g., "750mL bottle"). A lookup table of typical label dimensions yields pixels-per-mm. Cheap, ~80% accurate, fits the prototype budget.
   - **Better path**: detect a regulated reference element on the label (the Government Warning header is a good candidate — it has a known minimum size, so finding it lets us back-calculate scale).
   - **Best path**: ArUco markers or a reference card placed next to the label during photography. Out of scope for the app itself; documents a recommended capture protocol.
2. **Contrast ratio** — sample pixels inside the bounding box (text) versus a ring around it (background), compute the WCAG luminance ratio. ~5 lines of OpenCV.
3. **Field of vision (spirits)** — cluster bounding boxes and check whether brand + class/type + net contents fall within a single connected region. Heuristic: same horizontal band of the image. Imperfect but useful as a `Needs Review` trigger.

Each check produces a `Match | Needs Review | Mismatch` status using the existing vocabulary, plus a numeric measurement for the evidence panel ("type height: 1.7mm, minimum: 2mm").

#### Does the current architecture support it?

**Mostly yes, with two small additions:**

- ✅ **Pipeline stage slot exists.** The seven-stage pipeline was designed for this kind of insertion. New stage goes between attribution and extraction; no refactor.
- ✅ **Bounding boxes already flow through.** `OcrResult` carries them; today they stop at region attribution. Consuming them later is purely additive.
- ✅ **Status vocabulary already covers it.** `Match / Needs Review / Mismatch / Uncertain` maps cleanly onto legibility outcomes — "type too small" is `Mismatch`, "could not determine scale" is `Uncertain`.
- ⚠️ **Container-size input** on the upload form (or beverage-class default) is a new field. Small UI change; additive.
- ⚠️ **Calibration data plumbing.** A `LabelGeometry` value object (pixels-per-mm, container size, image DPI) computed once in preprocess and threaded through. The preprocess stage already has the image; this is one new return value.

#### Architectural risk

Legibility checks are the first place where the output depends on **physical units**, not just text. That means the deterministic guarantee gains one more variable — the calibration factor. If the calibration is wrong, every legibility check downstream is wrong. The mitigation is to make the calibration's confidence visible (`Uncertain` whenever the calibration itself was a fallback), which fits the existing confidence-tier model.

#### Phasing

- **Phase A**: contrast ratio only. No calibration needed — pure pixel check. Useful on its own; lowest risk.
- **Phase B**: type size with user-provided container size (easy path). Adds the `LabelGeometry` plumbing.
- **Phase C**: same-field-of-vision and reference-object auto-calibration.

## Longer-term

### 5. PDF input support

The prototype accepts PNG and JPG only. Reviewers sometimes receive label artwork as PDFs (typically single-page exports from Illustrator or InDesign). Adding support means:

- A rasterization step in `preprocess` using PyMuPDF (fast, no system deps) or pdf2image + poppler.
- Multi-page handling: either restrict to first page, or surface a page picker in the UI when N > 1.
- Content-Type re-enabled in `allowed_image_types`; corresponding frontend `accept` attribute change.

**Architectural impact**: small. Single new helper in `preprocess` that branches on `application/pdf` and converts to a PIL `Image` before the existing path resumes. Bumps Docker image size by ~10-30 MB depending on rasterizer choice.

### 6. COLA workflow awareness

The project brief explicitly excludes COLA *integration*, but the regulations reference Allowable Revisions (changes that do not require a new COLA). Useful prototype-level features:

- Mark a field "Allowable Revision" so reviewers see at a glance which mismatches do not need a new submission.
- Print-ready "summary of findings" PDF for attaching to a COLA file.

**Architectural impact**: a per-rule metadata flag (`allowable_revision: bool`) and a PDF reporter. Modest. Listed as longer-term because it leans into workflow assumptions outside the current prototype scope.

## Engineering / test coverage

### Real-OCR CI job

`backend/tests/test_sample_outcomes.py` exercises the eleven seeded sample scenarios end-to-end through the analysis pipeline. Under the default test suite (stub OCR provider) it can only assert structural validity of the response. The strongest assertions — per-field expected-status comparisons and Government Warning sub-codes against known-good labels — are gated behind the `real_ocr` pytest marker and skipped by default. A nightly CI job with cached PaddleOCR weights would run the gated path and surface regressions in the heuristic extractors and warning validator before they ship. **Architectural impact:** none; the marker and tests already exist. Pure CI work.

### Region-aware field extraction

The brand-name and class-of-fluid extractors today rely on token heuristics (title-case detection, keyword lists, exclusion of obvious non-brand patterns). They are fragile against stylized typography and ornamental layouts (see [tradeoffs.md](./tradeoffs.md#brandclass-of-fluid-heuristic-limits)). A layout-anchored replacement — "largest text region in the upper third of the label" for brand, "line immediately above or below the brand mark and not matching net-contents/ABV/warning patterns" for class-of-fluid — would consume the bounding-box data PaddleOCR already returns and produce more defensible extractions on real-world labels. Folds naturally into the legibility-check stage from #4 since both consume the same `LabelGeometry` plumbing.

## Folded into other items

These were considered as separate roadmap entries but fit better inside the rule packs in #1.

### 7. Disclosure-language library

Several disclosures have exact required wording the system should know about:

- Government Warning (already implemented).
- "Contains Sulfites" (wine).
- Color-additive disclosures (Yellow #5, Carmine, Cochineal Extract).
- "Contains FD&C Yellow No. 5" wording variants.
- Organic claims (USDA NOP — separate jurisdiction but same label).

Implemented as a string-set per rule pack; the existing Government Warning validator pattern generalizes.

### 8. Net-contents unit normalization

Beer requires pints; spirits require allowed metric fills; wine has its own list. A normalizer that knows the unit rules per beverage class would catch the "16 fl. oz." vs "1 pint" issue automatically. Lives inside each rule pack as part of net-contents validation.

## Source documents

- Wine — TTB 27 CFR Part 4 Labeling: https://www.ttb.gov/system/files/2025-12/Part_1.5_Labeling_--_FINAL.pdf
- Malt beverages — TTB 27 CFR Part 7 Labeling: https://www.ttb.gov/system/files/2024-04/Part_5_Labeling.pdf
- Distilled spirits — TTB 27 CFR Part 5 Labeling: https://www.ttb.gov/system/files/images/pdfs/presentations/part-4-labeling.pdf
