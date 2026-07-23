#!/usr/bin/env sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BACKEND_PID=
FRONTEND_PID=
STOPPING=false

cleanup() {
  if [ "$STOPPING" = true ]; then
    return
  fi
  STOPPING=true

  if [ -n "$BACKEND_PID" ] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
  if [ -n "$FRONTEND_PID" ] && kill -0 "$FRONTEND_PID" 2>/dev/null; then
    kill "$FRONTEND_PID" 2>/dev/null || true
  fi

  [ -z "$BACKEND_PID" ] || wait "$BACKEND_PID" 2>/dev/null || true
  [ -z "$FRONTEND_PID" ] || wait "$FRONTEND_PID" 2>/dev/null || true
}

trap cleanup EXIT INT TERM

if ! command -v python3 >/dev/null 2>&1; then
  echo "Errore: python3 non è installato o non è disponibile nel PATH." >&2
  exit 1
fi

if ! "$PROJECT_DIR/backend/.venv/bin/python" -c 'import uvicorn' >/dev/null 2>&1; then
  echo "Preparazione dell'ambiente Python del backend..."
  (
    cd "$PROJECT_DIR/backend"
    python3 -m venv --clear .venv
    .venv/bin/python -m pip install -e '.[dev]'
  )
fi

if [ ! -x "$PROJECT_DIR/frontend/node_modules/.bin/vite" ]; then
  if ! command -v npm >/dev/null 2>&1; then
    echo "Errore: npm non è installato o non è disponibile nel PATH." >&2
    exit 1
  fi
  echo "Installazione delle dipendenze del frontend..."
  (cd "$PROJECT_DIR/frontend" && npm install)
fi

(cd "$PROJECT_DIR/backend" && ./run-dev.sh) &
BACKEND_PID=$!

(cd "$PROJECT_DIR/frontend" && npm run dev -- --host 127.0.0.1) &
FRONTEND_PID=$!

echo "Backend:  http://localhost:8000"
echo "Frontend: http://localhost:5173"

# POSIX sh has no portable `wait -n`. Monitor both children so that a failed
# backend cannot leave Vite running with a broken /api proxy (and vice versa).
while kill -0 "$BACKEND_PID" 2>/dev/null && kill -0 "$FRONTEND_PID" 2>/dev/null; do
  sleep 1
done

if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
  wait "$BACKEND_PID"
else
  wait "$FRONTEND_PID"
fi
