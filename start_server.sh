#!/usr/bin/env bash
# Safe defaults for small VPS deployments (e.g. 2 GB DigitalOcean droplets).
# Usage: ./start_server.sh [port]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"
export NUMEXPR_NUM_THREADS="${NUMEXPR_NUM_THREADS:-1}"
export SOLVER_MAX_CELLS="${SOLVER_MAX_CELLS:-50000}"
export SOLVER_TIMEOUT_S="${SOLVER_TIMEOUT_S:-300}"
export SOLVER_MAX_RADIATION_OUTER="${SOLVER_MAX_RADIATION_OUTER:-1}"
export SOLVER_MIN_DX_MM="${SOLVER_MIN_DX_MM:-1.0}"
export SOLVER_MIN_DY_MM="${SOLVER_MIN_DY_MM:-1.0}"
export SOLVER_MIN_DZ_MM="${SOLVER_MIN_DZ_MM:-0.2}"
export SOLVER_MIN_TOLERANCE_K="${SOLVER_MIN_TOLERANCE_K:-0.0005}"
export SOLVER_MAX_LINEAR_ITERATIONS="${SOLVER_MAX_LINEAR_ITERATIONS:-4000}"

PORT="${1:-${PORT:-8000}}"

if [[ -d "$ROOT/venv/bin" ]]; then
  # shellcheck disable=SC1091
  source "$ROOT/venv/bin/activate"
elif [[ -d "$ROOT/.venv/bin" ]]; then
  # shellcheck disable=SC1091
  source "$ROOT/.venv/bin/activate"
fi

exec python3 server.py --port "$PORT"
