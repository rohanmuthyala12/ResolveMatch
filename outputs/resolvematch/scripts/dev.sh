#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install -r requirements.lock
if [ ! -f frontend/dist/index.html ]; then
  (cd frontend && npm ci --cache ../.local/npm-cache && npm run build)
fi
exec .venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
