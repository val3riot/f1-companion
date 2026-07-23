#!/usr/bin/env bash
set -Eeuo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
python_bin="${PYTHON_BIN:-$repo_dir/backend/.venv/bin/python}"

if [[ ! -x "$python_bin" ]]; then
  echo "Python non trovato in $python_bin. Imposta PYTHON_BIN." >&2
  exit 1
fi

cd "$repo_dir/backend"
"$python_bin" -m pytest -q tests
