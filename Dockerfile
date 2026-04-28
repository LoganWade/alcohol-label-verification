# =============================================================================
# Stage 1: frontend-builder
# Build the React/Vite frontend and produce a static dist/.
# =============================================================================
FROM node:20-slim AS frontend-builder

WORKDIR /build

# Install deps first (layer-cached until package*.json changes)
COPY frontend/package*.json ./
RUN npm ci

# Copy source and build with same-origin API base URL
COPY frontend/ ./
ENV VITE_API_BASE_URL=/api/v1
RUN npm run build


# =============================================================================
# Stage 2: backend-runtime
# Python 3.11 slim image; includes OpenCV/PaddleOCR system libs.
# =============================================================================
FROM python:3.11-slim AS backend-runtime

# System dependencies required by opencv-python-headless and PaddleOCR/Paddle
RUN apt-get update && apt-get install --no-install-recommends -y \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgomp1 \
    ccache \
    && rm -rf /var/lib/apt/lists/*

# Create the user that Hugging Face Spaces runs containers as (UID 1000)
RUN useradd -m -u 1000 user

ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

USER user
WORKDIR /home/user/app

# ------------------------------------------------------------------
# Install Python dependencies
# Copy only the package metadata first so pip install is layer-cached
# until pyproject.toml or the app source changes.
# ------------------------------------------------------------------
COPY --chown=user backend/pyproject.toml backend/README.md ./backend/
COPY --chown=user backend/app ./backend/app

RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir ./backend

# ------------------------------------------------------------------
# Pre-download PaddleOCR model weights at build time so cold starts
# are fast.  The models (~200 MB) are cached inside the image under
# ~/.paddleocr (i.e. /home/user/.paddleocr).
#
# If the build network blocks outbound HTTPS, this step will fail with
# a connection error.  Rather than failing the entire image build, we
# write a sentinel file (.paddle_preload_failed) which the /health
# endpoint surfaces so deploy operators can see that models will be
# fetched on first request instead.  The container still starts and
# serves traffic (PaddleOCR will lazy-download on first call).
# Alternatively, mount a paddle_models/ volume at /home/user/.paddleocr.
# ------------------------------------------------------------------
RUN python -c "from paddleocr import PaddleOCR; PaddleOCR(use_angle_cls=True, lang='en', show_log=False)" \
    || ( echo "WARNING: PaddleOCR weight pre-download failed (likely network restriction). Models will be downloaded on first use." \
         && touch /home/user/app/.paddle_preload_failed )

# ------------------------------------------------------------------
# Copy built frontend and sample data
# ------------------------------------------------------------------
COPY --chown=user --from=frontend-builder /build/dist ./frontend_dist
COPY --chown=user sample_data ./sample_data

# ------------------------------------------------------------------
# Runtime environment variables
# ------------------------------------------------------------------
ENV ALV_OCR_PROVIDER=paddle
ENV ALV_SAMPLES_DIR=/home/user/app/sample_data
ENV ALV_STATIC_DIR=/home/user/app/frontend_dist
ENV PORT=7860

# PaddlePaddle CPU build threading.
#
# HF Spaces sets OMP_NUM_THREADS=2 by default on its CPU instances. Paddle's
# own startup warning explicitly says this fails when the binary is compiled
# against OpenBlas ("It will fail if this PaddlePaddle binary is compiled
# with OpenBlas since OpenBlas does not support multi-threads"). With
# OMP_NUM_THREADS=2 plus concurrent .ocr() calls we observed deterministic
# SIGSEGVs inside paddle::AnalysisPredictor::ZeroCopyRun().
#
# Pinning OMP/MKL to 1 thread, combined with cpu_threads=1 in the PaddleOCR
# constructor and a process-wide lock around .ocr() in paddle_ocr.py, makes
# inference single-threaded and crash-free on the free-tier 2-vCPU runtime.
# Concurrency on the HTTP layer is preserved via asyncio.to_thread (concurrent
# reviews queue at the OCR step but /health and /samples stay responsive).
ENV OMP_NUM_THREADS=1
ENV MKL_NUM_THREADS=1

EXPOSE 7860

CMD ["uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "7860"]
