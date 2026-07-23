#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")"
.venv/bin/uvicorn app.main:app --reload --port 8000
