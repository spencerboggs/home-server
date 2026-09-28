#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
git pull --ff-only
python3 "$ROOT/scripts/render_runtime.py"
exec bash "$ROOT/scripts/up.sh" core
