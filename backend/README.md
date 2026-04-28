# Backend

FastAPI service implementing the extraction → validation → reporting pipeline described in [`docs/architecture.md`](../docs/architecture.md).

## Status

**Phase 1 — skeleton.** Typed schemas, the OCR provider interface, stage-level service interfaces, and a stub pipeline are in place. The analyze endpoint returns a deterministic stub response so the frontend can be developed against a real contract. Real OCR and field extraction land in Phase 2.

## Layout

```text
app/
├── api/                   # FastAPI routers (health, reviews)
├── core/                  # Settings, constants (status vocabulary, thresholds)
├── schemas/               # Pydantic request/response models
├── services/
│   ├── extraction/        # preprocess, ocr, region_attribution, field_extraction
│   ├── validation/        # comparison, warning_validator, normalizers
│   └── reporting/         # response aggregation
├── utils/                 # cross-cutting helpers (timing, ids)
└── main.py                # FastAPI app factory
tests/                     # pytest tests pinned to the API and stage contracts
```

## Run locally

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
```

OpenAPI: http://localhost:8000/docs

## Tests

```bash
pytest
```
