#!/usr/bin/env bash
# Start Earth Evidence Atlas locally. Usage: scripts/run.sh [port] [host]
set -euo pipefail
cd "$(dirname "$0")/.."
source .venv/bin/activate
exec uvicorn atlas.api:app --host "${2:-127.0.0.1}" --port "${1:-8765}"
