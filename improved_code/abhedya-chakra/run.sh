#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# ABHEDYA-CHAKRA — one-command bring-up.
#
# The sandbox wipes installed packages and node_modules between sessions but
# keeps the source tree and data/. This script makes the restart idempotent:
# it installs only what is missing, then execs the requested server.
#
#   ./run.sh deps   install backend + both frontend dependency sets if missing
#   ./run.sh api    start FastAPI on 0.0.0.0:8000
#   ./run.sh web    start the full workstation UI on 0.0.0.0:5173
#   ./run.sh demo   start the simple demo UI on 0.0.0.0:5174
#   ./run.sh all    start all three at once and keep them together
#
# Add ABHEDYA_NO_AUTOLOAD=1 before './run.sh api' to skip the boot-time ingest
# so the demo UI's Data tab performs the load explicitly.
# ---------------------------------------------------------------------------
set -euo pipefail
cd "$(dirname "$0")"

ensure_backend() {
  python3 -c "import fastapi, uvicorn, duckdb, polars, numpy" 2>/dev/null \
    || pip install -q -r backend/requirements.txt
}

ensure_frontend() {
  [ -x frontend/node_modules/.bin/vite ] \
    || (cd frontend && npm install --no-audit --no-fund --silent)
}

ensure_demo() {
  [ -x frontend-demo/node_modules/.bin/vite ] \
    || (cd frontend-demo && npm install --no-audit --no-fund --silent)
}

# Start everything under one process so a single restart brings the whole demo
# back. Children are killed together, so no port is left bound by an orphan.
run_all() {
  ensure_backend; ensure_frontend; ensure_demo
  pids=()
  ( cd backend && exec python3 -m uvicorn app.main:app \
      --host 0.0.0.0 --port 8000 --log-level warning ) & pids+=($!)
  ( cd frontend && exec npm run dev -- --host 0.0.0.0 --port 5173 ) & pids+=($!)
  ( cd frontend-demo && exec npm run dev -- --host 0.0.0.0 --port 5174 ) & pids+=($!)
  trap 'kill "${pids[@]}" 2>/dev/null || true' INT TERM EXIT
  echo "api :8000 · workstation :5173 · demo :5174"
  wait
}

case "${1:-deps}" in
  deps) ensure_backend; ensure_frontend; ensure_demo; echo "dependencies ready" ;;
  api)  ensure_backend
        cd backend
        exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-level warning ;;
  web)  ensure_frontend
        cd frontend
        exec npm run dev -- --host 0.0.0.0 --port 5173 ;;
  demo) ensure_demo
        cd frontend-demo
        exec npm run dev -- --host 0.0.0.0 --port 5174 ;;
  all)  run_all ;;
  *)    echo "usage: ./run.sh {deps|api|web|demo|all}" >&2; exit 2 ;;
esac
