# API image, built from the REPO ROOT so the sibling directories the API
# imports at runtime actually ship:
#   packages/   matching engine, extraction, scraper, verification
#   scripts/    recompute_matches.py, invoked by the scheduler
#   SCORING_CONFIG.yaml  gate rules + dimension weights
#
# Railway's Root Directory must be the repo root for this to build. With the
# root as build context, Nixpacks would otherwise detect the top-level
# package.json and build a Node app, so this Dockerfile pins Python explicitly.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first so the layer caches across code-only changes.
COPY apps/api/requirements.txt ./apps/api/requirements.txt
RUN pip install --upgrade pip && pip install -r apps/api/requirements.txt

COPY apps/api/ ./apps/api/
COPY packages/ ./packages/
COPY scripts/ ./scripts/
COPY SCORING_CONFIG.yaml ./SCORING_CONFIG.yaml

# The app resolves packages/ and scripts/ by walking up from its own file, so
# it finds them at /app regardless of where uvicorn is launched from.
WORKDIR /app/apps/api

EXPOSE 8000
# No shell: serve.py reads PORT from the environment itself.
CMD ["python", "serve.py"]
