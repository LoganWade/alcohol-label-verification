# Test data

The prototype is exercised with a mix of synthetic and public-reference label imagery, paired with expected-fields JSON. Sample assets live in `sample_data/` and are committed to the repository.

## Provenance

- **Synthetic labels** — generated specifically for this project to cover edge cases that would be hard to find in public imagery. Each synthetic label is documented with the generation prompt or process so the asset is reproducible.
- **Public reference imagery** — sourced from TTB public guidance pages or other clearly public examples. Provenance and source URL recorded per file.

No real label submissions, no PII, no proprietary brand assets are included.

## Scenario matrix

The seeded set is **eleven single-label samples** plus **one importer batch sample**. The single-label set is split into eight synthetic scenarios (designed to exercise every status the pipeline can return) and three TTB reference labels (real public imagery, included so the deployed app shows the pipeline running on something other than synthetic data).

### Synthetic scenarios (8)

| Sample id | Title | Image quality | Expected outcome | Purpose |
|---|---|---|---|---|
| `clean_match` | Clean match | Clean, high contrast | All fields `Match`, warning `Match` | Happy path; smoke test |
| `case_only_brand` | Brand name — case only | Clean | Brand `Match (normalized)`, others `Match` | Validates Dave's "STONE'S THROW vs Stone's Throw" case |
| `typo_brand` | Brand name — single typo | Clean | Brand `Needs Review` | Validates fuzzy threshold tier |
| `abv_mismatch` | ABV mismatch | Clean | ABV `Mismatch`, others `Match` | Validates structured-field comparison |
| `warning_titlecase` | Government Warning — title-case header | Clean | Warning `Mismatch`, others `Match` | Validates Jenny's strict-header rule |
| `warning_missing` | Government Warning — missing | Clean | Warning `Missing`, others may match | Validates required-field detection |
| `skewed_lowlight` | Skewed / poorly lit photo | Noisy | Several fields `Needs Review` or `Uncertain` | Validates confidence propagation |
| `unreadable` | Unreadable image | Failed | Fields `Uncertain`, recovery message | Validates failure path |

### TTB reference labels (3)

| Sample id | Title | Provenance |
|---|---|---|
| `ttb_wine_reference` | TTB reference — Merlot wine label | TTB public guidance imagery |
| `ttb_table_wine_reference` | TTB reference — Table wine label | TTB public guidance imagery |
| `ttb_beer_reference` | TTB reference — Beer front label | TTB public guidance imagery |

### Importer batch (1)

| Sample id | Title | Purpose |
|---|---|---|
| `batch_demo` | Importer batch — 4 applications | Exercises the manifest parser, the queue, and the bulk-approve action with a small mixed-outcome batch |

## File layout

```text
sample_data/manifest.json                # single-label sample list (11 entries)
sample_data/batch-manifest.json          # importer batch sample list (1 entry)
sample_data/labels/<sample_id>.png       # single-label images
sample_data/expected_fields/<sample_id>.json
sample_data/batch_demo/manifest.csv      # importer-style CSV manifest
sample_data/batch_demo/<image>.png       # batch images referenced by manifest rows
```

The single-label samples are surfaced by the API at `/api/v1/samples/` and rendered as cards on the home page. They are not used by the batch flow — the batch flow ingests its own CSV manifest (see `docs/demo-script.md` § 6a for the column list), and `sample_data/batch_demo/` is the example payload of that shape.

## Adding new samples

1. Place the image in `sample_data/labels/`.
2. Place the expected fields JSON in `sample_data/expected_fields/` with the same base name.
3. Add an entry to `sample_data/manifest.json` with `id`, `title`, `description`, `expected_outcome`, and the two paths.
4. Add a row to the scenario matrix above with the expected outcome.
5. If the asset has external provenance, add a one-line note to `sample_data/labels/PROVENANCE.md`.
