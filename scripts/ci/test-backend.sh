#!/usr/bin/env bash
set -Eeuo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
python_bin="${PYTHON_BIN:-$repo_dir/backend/.venv/bin/python}"

# Se PYTHON_BIN è un comando come "python" o "python3",
# risolvilo tramite PATH. Se è un percorso, validalo direttamente.
if [[ "$python_bin" != */* ]]; then
  if ! python_bin="$(command -v "$python_bin")"; then
    echo "Python non trovato nel PATH: ${PYTHON_BIN:-python}" >&2
    exit 1
  fi
elif [[ ! -x "$python_bin" ]]; then
  echo "Python non trovato o non eseguibile: $python_bin" >&2
  exit 1
fi

cd "$repo_dir/backend"
exec "$python_bin" -m pytest -q tests
