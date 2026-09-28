#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run: sudo bash scripts/down.sh media"
  exit 1
fi

if [[ $# -ne 1 || "$1" == "core" ]]; then
  echo "Usage: sudo bash scripts/down.sh media|git|collab|games|ai|discord|deploy|cache"
  echo "Core stays up. Stop the whole stack with: docker compose --profile core down"
  exit 1
fi

name="$1"
profiles_file="$ROOT/config/profiles"
if [[ -f "$profiles_file" ]]; then
  grep -vx "$name" "$profiles_file" > "${profiles_file}.tmp" || true
  mv "${profiles_file}.tmp" "$profiles_file"
fi

case "$name" in
  media) docker stop server-jellyfin || true ;;
  git) docker stop server-forgejo server-forgejo-db || true ;;
  collab) docker stop server-nextcloud server-nextcloud-db server-collabora || true ;;
  games) docker stop server-minecraft || true ;;
  ai)
    docker stop server-vllm server-vllm-manager server-llmlingua server-gpu-exporter || true
    if [[ -f "$profiles_file" ]]; then
      grep -vx "ai-manager" "$profiles_file" > "${profiles_file}.tmp" || true
      mv "${profiles_file}.tmp" "$profiles_file"
    fi
    ;;
  discord) docker stop server-discord-bot server-lavalink || true ;;
  deploy) docker stop server-coolify server-coolify-realtime server-coolify-db server-coolify-redis || true ;;
  cache) docker stop server-lancache || true ;;
  *)
    echo "Unknown profile: $name"
    exit 1
    ;;
esac

python3 "$ROOT/scripts/render_runtime.py"
docker compose --profile core up -d caddy
