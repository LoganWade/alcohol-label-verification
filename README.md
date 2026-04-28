---
title: Alcohol Label Verification
emoji: 🍷
colorFrom: red
colorTo: gray
sdk: docker
app_port: 7860
---

# Alcohol Label Verification

AI-powered prototype that helps compliance reviewers verify whether information on an alcohol label matches expected application data and whether required label content is present. Built as a take-home project for an interview process.

> **Status:** In development. Discovery and architecture docs are complete; backend and frontend implementation in progress.

## Why this exists

The TTB reviews ~150,000 label applications a year with ~47 agents. Much of the work is straightforward visual matching: brand name on the form vs brand name on the label, ABV on the form vs ABV on the label, and verifying that the mandatory Government Health Warning is present, exact, and properly formatted. This prototype is a standalone proof-of-concept exploring whether AI-assisted comparison can give reviewers a faster, more confident pass on the routine fields so they can spend their time on the cases that need real judgment.

## Design priorities

Three constraints shaped every technical choice, drawn from stakeholder interviews captured in the assignment:

1. **Speed.** A prior vendor pilot took 30–40 seconds per label and the team reverted to manual review. Single-label analysis must complete in roughly 5 seconds.
2. **Trust.** Reviewers need to see *why* the system reached a conclusion. Every comparison is traceable to the cropped region of the original image, the raw OCR text, and the rule that decided the outcome.
3. **Calm, accessible UX.** Half the team is over 50; tech comfort varies widely. The UI is built around a single linear flow, plain language, and WCAG 2.2 AA accessibility.

## Approach (one-paragraph version)

A FastAPI backend exposes a single `/api/v1/reviews/analyze` endpoint that runs a named, multi-stage extraction pipeline (preprocess → OCR → region attribution → field extraction → comparison → warning validation → reporting). OCR is local-only (PaddleOCR) so there are no outbound network dependencies — a hard requirement in federal environments. Comparison logic is fully deterministic, using Unicode normalization plus `rapidfuzz` for tiered matching, with a dedicated validator for the Government Warning. A React + Vite frontend presents a three-step linear flow (expected fields → upload → results) with side-by-side evidence, status chips, and per-field confidence. No LLM is used in the decision path; every result is inspectable and reproducible.

## Documentation

- [Architecture](docs/architecture.md) — system design, pipeline stages, API contract, key decisions
- [Trade-offs](docs/tradeoffs.md) — what we chose, what we deferred, and why
- [Test data](docs/test-data.md) — sample labels, provenance, and the test scenario matrix
- [Demo script](docs/demo-script.md) — how to walk through the deployed app

## Repository layout

```text
.
├── AGENTS.md              # Operating manual for coding agents on this project
├── Dockerfile             # Multi-stage build: Node 20 frontend + Python 3.11 backend
├── README.md
├── docs/                  # Architecture, trade-offs, test data, demo script
├── frontend/              # React + Vite + TypeScript UI
├── backend/               # FastAPI service + extraction/validation pipeline
├── sample_data/           # Sample labels and paired expected-fields JSON
└── scripts/               # Dev and deploy helpers
```

## Setup

> Detailed setup instructions land alongside the first working build. Stack: Python 3.11 + FastAPI + PaddleOCR + OpenCV; Node 20 + React + Vite + TypeScript; Docker for deployment to Hugging Face Spaces.

## Deployment (Hugging Face Spaces)

This app deploys as a single Docker container to [Hugging Face Spaces](https://huggingface.co/spaces) using the `sdk: docker` Space type. When you push the repo to an HF Space remote, Hugging Face detects the `Dockerfile` automatically (via the `sdk: docker` line in the README frontmatter), builds the image in the cloud, and serves it at `https://<hf-username>-<space-name>.hf.space`. The container listens on port 7860 (set in the `app_port` frontmatter field). FastAPI serves both the REST API at `/api/v1/*` and the pre-built React frontend as static files at `/`, so no separate static host or CDN is required.

The first deploy takes roughly 5–10 minutes because the image build includes downloading the PaddleOCR English model weights (~200 MB) and baking them into the image. Subsequent deploys reuse the Docker layer cache and are significantly faster.

```bash
# One-time setup
pip install huggingface_hub
huggingface-cli login
# Then create the Space via web UI: huggingface.co/new-space, Docker SDK
git remote add hf https://huggingface.co/spaces/<user>/<space-name>
git push hf main
```

After the build completes the app is live at `https://<user>-<space-name>.hf.space`.

## Status & limitations

This is a prototype, not production software. It is **not** legally compliant for live regulatory review, does not integrate with COLA, and does not store or transmit personally identifiable information. See [Trade-offs](docs/tradeoffs.md) for a full list of known limitations.
