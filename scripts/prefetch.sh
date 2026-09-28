#!/usr/bin/env bash
# Download apt packages and container images onto Ubuntu Server.
# Usage:
#   sudo bash scripts/prefetch.sh
#   sudo bash scripts/prefetch.sh core media git collab
#   sudo bash scripts/prefetch.sh all
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run: sudo bash scripts/prefetch.sh"
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is not installed. Finish server_setup_guide.md section 11 first."
  exit 1
fi

echo "Installing Ubuntu packages"
apt-get update
apt-get install -y git python3 mergerfs ca-certificates curl parted e2fsprogs

profiles=("$@")
if [[ ${#profiles[@]} -eq 0 ]]; then
  profiles=(core)
fi
if [[ "${profiles[0]}" == "all" ]]; then
  profiles=(core media git collab games ai discord deploy cache)
fi

pull() {
  echo "docker pull $1"
  docker pull "$1"
}

need_core=0
need_media=0
need_git=0
need_collab=0
need_games=0
need_ai=0
need_discord=0
need_deploy=0
need_cache=0

for name in "${profiles[@]}"; do
  case "$name" in
    core) need_core=1 ;;
    media) need_media=1 ;;
    git) need_git=1 ;;
    collab) need_collab=1 ;;
    games) need_games=1 ;;
    ai) need_ai=1 ;;
    discord) need_discord=1 ;;
    deploy) need_deploy=1 ;;
    cache) need_cache=1 ;;
    *)
      echo "Unknown profile: $name"
      exit 1
      ;;
  esac
done

if [[ "$need_core" -eq 1 ]]; then
  pull postgres:16-alpine
  pull ghcr.io/goauthentik/server:2026.8.3
  pull redis:7-alpine
  pull prom/prometheus:v3.4.0
  pull grafana/grafana:11.6.0
  pull grafana/loki:3.4.2
  pull grafana/promtail:3.4.2
  pull prom/node-exporter:v1.9.1
  pull gcr.io/cadvisor/cadvisor:v0.49.1
  pull binwiederhier/ntfy:v2.14.0
  pull caddy:2-builder-alpine
  pull caddy:2-alpine
  pull node:22-alpine
  pull python:3.12-slim
fi

if [[ "$need_media" -eq 1 ]]; then
  pull jellyfin/jellyfin:10.10.7
fi

if [[ "$need_git" -eq 1 ]]; then
  pull postgres:16-alpine
  pull codeberg.org/forgejo/forgejo:11
fi

if [[ "$need_collab" -eq 1 ]]; then
  pull postgres:16-alpine
  pull nextcloud:31-apache
  pull collabora/code:latest
fi

if [[ "$need_games" -eq 1 ]]; then
  pull itzg/minecraft-server:java21
fi

if [[ "$need_ai" -eq 1 ]]; then
  pull vllm/vllm-openai:latest
  pull nvidia/dcgm-exporter:latest
  pull python:3.12-slim
  echo "LLMLingua also downloads PyTorch during: sudo bash scripts/up.sh ai"
fi

if [[ "$need_discord" -eq 1 ]]; then
  pull ghcr.io/lavalink-devs/lavalink:4
  pull python:3.12-slim
fi

if [[ "$need_deploy" -eq 1 ]]; then
  pull postgres:15-alpine
  pull redis:7-alpine
  pull coollabsio/coolify:latest
  pull coollabsio/coolify-realtime:1.0.19
fi

if [[ "$need_cache" -eq 1 ]]; then
  pull lancachenet/monolithic:latest
fi

echo "Downloads finished."
