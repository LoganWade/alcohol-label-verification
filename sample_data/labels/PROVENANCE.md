# Sample Label Provenance

This file documents the origin of every label image in `sample_data/labels/`.

---

## Synthetic labels (provenance: `synthetic`)

The following 8 PNG files were generated programmatically by
`scripts/generate_samples.py` using Pillow. They contain no real brand
imagery or proprietary content. All text is invented for testing purposes.

| File | Scenario |
|---|---|
| `clean_match.png` | All fields match exactly |
| `case_only_brand.png` | Brand name differs only in capitalisation |
| `typo_brand.png` | Brand name has a single extra character |
| `abv_mismatch.png` | ABV value on label differs from expected |
| `warning_titlecase.png` | Government Warning header in title-case instead of ALL-CAPS |
| `warning_missing.png` | Government Warning statement absent from label |
| `skewed_lowlight.png` | Clean-match content with rotation, contrast reduction, blur, and noise |
| `unreadable.png` | Nearly-black image — preprocessing classifies as FAILED |

---

## TTB public reference labels (provenance: `public_ttb_reference`)

The following images are cropped from **publicly available TTB educational
and reference materials**. They are reproduced here solely for
non-commercial, educational testing of label-review software, consistent
with the TTB's stated purpose in publishing these reference documents.

### `ttb_wine_reference.png`

- **Content:** "Sample Standard One-Piece Wine Brand Label" — ABC WINES /
  AMERICAN MERLOT (figure from Wine BAM Chapter 10, page 4)
- **Source URL:** <https://www.ttb.gov/system/files/images/pdfs/wine_bam/c10-sample-wine-labels.pdf>
- **Retrieval date:** 2026-04-28
- **Classification:** TTB public reference imagery (Beverage Alcohol Manual,
  Wine chapter)

### `ttb_table_wine_reference.png`

- **Content:** "Sample Table Wine Brand Label" — XYZ WINERY / RED TABLE WINE
  (figure from Wine BAM Chapter 10, page 2)
- **Source URL:** <https://www.ttb.gov/system/files/images/pdfs/wine_bam/c10-sample-wine-labels.pdf>
- **Retrieval date:** 2026-04-28
- **Classification:** TTB public reference imagery (Beverage Alcohol Manual,
  Wine chapter)

### `ttb_beer_reference.png`

- **Content:** Front label example — "Example" / "Golden Ale" / Fake Brewery
  Name (from TTB Boot Camp for Brewers: Labeling presentation, slide 19)
- **Source URL:** <https://www.ttb.gov/images/pdfs/TTB_Boot_Camp_for_Brewers-_Labeling.pdf>
- **Retrieval date:** 2026-04-28
- **Classification:** TTB public reference imagery (TTB educational Boot Camp
  presentation)

---

## Note on spirits reference imagery

The TTB Distilled Spirits Beverage Alcohol Manual (BAM) was reviewed but
contains only text-based reference tables and no rendered label illustrations.
No usable spirits label image was found after checking the Spirits BAM
(`complete-distilled-spirit-beverage-alcohol-manual.pdf`), the Beer BAM, and
the TTB COLA Online registry. The Beer BAM sample label is used as the third
TTB reference label in lieu of a spirits example.
