#!/usr/bin/env bash
# Stop AI containers without using the dashboard or a model.
set -euo pipefail
ids="$(docker ps -q --filter label=ai-model=true)"
if [[ -z "$ids" ]]; then
  echo "No AI containers are running."
  exit 0
fi
# shellcheck disable=SC2086
docker stop $ids
echo "AI containers stopped. The dashboard, files, and proxy are still up."
