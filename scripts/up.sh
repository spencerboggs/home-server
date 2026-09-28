#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run: sudo bash scripts/up.sh core"
  exit 1
fi

if [[ $# -eq 0 ]]; then
  echo "Usage: sudo bash scripts/up.sh core|media|git|collab|games|ai|discord|deploy|cache"
  exit 1
fi

if [[ ! -f .env ]]; then
  echo "Missing .env. Run sudo bash scripts/setup.sh first."
  exit 1
fi

python3 "$ROOT/scripts/generate_env.py"

set -a
# shellcheck disable=SC1091
source .env
set +a

profiles_file="$ROOT/config/profiles"
if [[ ! -f "$profiles_file" ]]; then
  cp "$ROOT/config/profiles.default" "$profiles_file"
fi

extra_files=()
for name in "$@"; do
  case "$name" in
    core|media|git|collab|games|ai|discord|deploy) ;;
    cache) extra_files+=(-f "$ROOT/compose/lancache.yml") ;;
    *)
      echo "Unknown profile: $name"
      exit 1
      ;;
  esac
  if [[ "$name" == "ai" ]]; then
    if [[ -z "${VLLM_MODEL:-}" ]]; then
      echo "Set VLLM_MODEL in .env before starting the ai profile."
      exit 1
    fi
    if ! command -v nvidia-smi >/dev/null 2>&1; then
      echo "nvidia-smi is not available. Install the driver and NVIDIA Container Toolkit first."
      exit 1
    fi
    if [[ -n "${VLLM_MANAGER_MODEL:-}" ]]; then
      export VLLM_GPU_UTIL=0.65
      if ! grep -qx "ai-manager" "$profiles_file"; then
        echo "ai-manager" >> "$profiles_file"
      fi
    fi
  fi
  if [[ "$name" == "games" && "${MINECRAFT_EULA:-FALSE}" != "TRUE" ]]; then
    echo "Set MINECRAFT_EULA=TRUE in .env after you accept the Minecraft EULA."
    exit 1
  fi
  if [[ "$name" == "discord" && -z "${DISCORD_TOKEN:-}" ]]; then
    echo "Set DISCORD_TOKEN in .env before starting the discord profile."
    exit 1
  fi
  if [[ "$name" == "cache" && -z "${LANCACHE_BIND_IP:-}" ]]; then
    echo "Set LANCACHE_BIND_IP to a second address, not the address Caddy uses."
    exit 1
  fi
  if ! grep -qx "$name" "$profiles_file"; then
    echo "$name" >> "$profiles_file"
  fi
done

if grep -qx "ai-manager" "$profiles_file"; then
  if [[ -z "${VLLM_MANAGER_MODEL:-}" ]]; then
    echo "config/profiles lists ai-manager. Set VLLM_MANAGER_MODEL or remove that line."
    exit 1
  fi
  export VLLM_GPU_UTIL=0.65
fi

python3 "$ROOT/scripts/render_runtime.py"

args=(--profile core)
while read -r name; do
  [[ -z "$name" || "$name" == "core" || "$name" == "cache" ]] && continue
  args+=(--profile "$name")
done < "$profiles_file"

docker compose -f "$ROOT/docker-compose.yml" "${extra_files[@]}" "${args[@]}" up -d --build
bash "$ROOT/scripts/configure-sso.sh"
docker compose -f "$ROOT/docker-compose.yml" "${extra_files[@]}" "${args[@]}" ps
