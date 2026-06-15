#!/usr/bin/env bash
# Launch Version4 on port 8000 (replaces the older root server.py entry point).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$ROOT/New_Version4 _User_accounts/start_server.sh" "$@"
