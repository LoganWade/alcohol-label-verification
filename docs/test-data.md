# Test data

The prototype is exercised with a mix of synthetic and public-reference label imagery, paired with expected-fields JSON. Sample assets live in `sample_data/` and are committed to the repository.

## Provenance

- **Synthetic labels** — generated specifically for this project to cover edge cases that would be hard to find in public imagery. Each synthetic label is documented with the generation prompt or process so the asset is reproducible.
- **Public reference imagery** — sourced from TTB public guidance pages or other clearly public examples. Provenance and source URL recorded per file.

No real label submissions, no PII, no proprietary brand assets are included.

## Scenario matrix

The samples are designed to exercise every status the system can return. At minimum, the seeded set covers:

| Scenario | Image quality | Expected outcome | Purpose |
|---|---|---|---|
| Clean match | Clean, high contrast | All fields `Match`, warning `Match` | Happy path; smoke test |
| Case-only difference on brand | Clean | Brand `Match (normalized)`, others `Match` | Validates Dave's "STONE'S THROW vs Stone's Throw" case |
| Single-character typo on brand | Clean | Brand `Needs Review` | Validates fuzzy threshold tier |
| ABV mismatch | Clean | ABV `Mismatch`, others `Match` | Validates structured-field comparison |
| Government Warning, title case header | Clean | Warning `Mismatch`, others `Match` | Validates Jenny's strict-header rule |
| Government Warning, missing | Clean | Warning `Missing`, others may match | Validates required-field detection |
| Skewed / poorly lit photo | Noisy | Several fields `Needs Review` or `Uncertain` | Validates confidence propagation |
| Unreadable image | Failed | All fields `Uncertain`, recovery message | Validates failure path |

## File naming convention

```text
sample_data/labels/<scenario_id>.png
sample_data/expected_fields/<scenario_id>.json
```

Pairing by filename so the batch flow can match them automatically.

## Adding new samples

1. Place the image in `sample_data/labels/`.
2. Place the expected fields JSON in `sample_data/expected_fields/` with the same base name.
3. Add a row to the scenario matrix above with the expected outcome.
4. If the asset has external provenance, add a one-line note to `sample_data/labels/PROVENANCE.md`.
