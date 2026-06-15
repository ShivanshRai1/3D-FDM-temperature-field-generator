#!/usr/bin/env bash
# Version4 production startup for DigitalOcean / VPS (default port 8000).
# Usage: ./start_server.sh [port]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"
export NUMEXPR_NUM_THREADS="${NUMEXPR_NUM_THREADS:-1}"
export HOST="${HOST:-0.0.0.0}"
export PORT="${1:-${PORT:-8000}}"

if [[ -d "$ROOT/venv/bin" ]]; then
  # shellcheck disable=SC1091
  source "$ROOT/venv/bin/activate"
elif [[ -d "$ROOT/.venv/bin" ]]; then
  # shellcheck disable=SC1091
  source "$ROOT/.venv/bin/activate"
elif [[ -d "$ROOT/../venv/bin" ]]; then
  # shellcheck disable=SC1091
  source "$ROOT/../venv/bin/activate"
fi

exec python3 server.py --host "$HOST" --port "$PORT"
