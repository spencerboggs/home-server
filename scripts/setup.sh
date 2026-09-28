#!/usr/bin/env bash
# First bring-up after Ubuntu, Tailscale, UFW, the VLAN, and Docker are in place.
# Usage: sudo bash scripts/setup.sh --format-bulk
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run: sudo bash scripts/setup.sh --format-bulk"
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is not installed. Finish that step in server_setup_guide.md first."
  exit 1
fi

apt-get update
apt-get install -y git python3 mergerfs ca-certificates curl parted e2fsprogs

bash "$ROOT/scripts/storage/layout.sh" "$@"

mkdir -p \
  /srv/server/apps \
  /srv/server/data/authentik/postgres \
  /srv/server/data/authentik/media \
  /srv/server/data/dashboard \
  /srv/server/data/caddy \
  /srv/server/data/grafana \
  /srv/server/data/prometheus \
  /srv/server/data/loki \
  /srv/server/data/ntfy \
  /srv/server/data/jellyfin/config \
  /srv/server/data/jellyfin/cache \
  /srv/server/data/forgejo/postgres \
  /srv/server/data/forgejo/data \
  /srv/server/data/nextcloud/postgres \
  /srv/server/data/nextcloud/html \
  /srv/server/data/coolify
mkdir -p \
  /srv/bulk/backups \
  /data/coolify/source \
  /data/coolify/ssh \
  /data/coolify/applications \
  /data/coolify/databases \
  /data/coolify/services \
  /data/coolify/backups \
  /data/coolify/images

if id "${SUDO_USER:-}" >/dev/null 2>&1; then
  chown -R "${SUDO_USER}:${SUDO_USER}" /srv/bulk/media /srv/bulk/storage /srv/server/apps || true
fi

python3 "$ROOT/scripts/generate_env.py"
python3 "$ROOT/scripts/render_runtime.py"

if systemctl list-unit-files caddy.service >/dev/null 2>&1; then
  if systemctl is-active --quiet caddy; then
    echo "Stopping the apt Caddy service so the container can bind ports 80 and 443."
    systemctl disable --now caddy
  fi
fi

docker compose --profile core up -d --build

echo
echo "Core services are starting. Authentik can take a minute."
bash "$ROOT/scripts/configure-authentik.sh" || echo "Authentik bootstrap did not finish. Check: docker logs server-authentik"

python3 - <<'PY'
from pathlib import Path
env = {}
for line in Path(".env").read_text().splitlines():
    if not line.strip() or line.strip().startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    env[key] = value
print()
print("Dashboard host:", env.get("DASHBOARD_HOST"))
print("Authentik host:", env.get("AUTH_HOST"))
print("Bootstrap admin username: akadmin")
print("Bootstrap admin password is AUTHENTIK_BOOTSTRAP_PASSWORD in .env")
print()
if env.get("DASHBOARD_HOST", "").endswith("example.com"):
    print("Edit .env and replace example.com with your domain, then run:")
    print("  sudo bash scripts/up.sh core")
print("Enable one group at a time:")
print("  sudo bash scripts/up.sh media")
print("  sudo bash scripts/up.sh git")
print("  sudo bash scripts/up.sh collab")
print("  sudo bash scripts/up.sh games")
print("  sudo bash scripts/up.sh ai")
print("  sudo bash scripts/up.sh discord")
print("  sudo bash scripts/up.sh deploy")
PY
