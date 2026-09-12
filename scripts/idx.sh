#!/usr/bin/env bash
# IDX data-plane CLI wrapper (local): loads blackheart-ingest/idx-local.env and runs the ingest venv.
#   scripts/idx.sh migrate | status | universe | daily --date D | index --date D | backfill --from D [--to D] [--index] | replay ...
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
set -a; source "$ROOT/blackheart-ingest/idx-local.env"; set +a
export PYTHONIOENCODING=utf-8
cd "$ROOT/blackheart-ingest"
exec .venv/Scripts/python -m blackheart_ingest.idx.cli "$@"
