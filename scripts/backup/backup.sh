#!/usr/bin/env bash
# Copy the data that cannot be rebuilt onto BACKUP_TARGET.
# A copy that stays on this machine is not the backup.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

if [[ -z "${BACKUP_TARGET:-}" ]]; then
  echo "Set BACKUP_TARGET in .env to a disk or host that is not this server."
  echo "Refusing to store the only backup on /srv/bulk."
  exit 2
fi

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
dest="${BACKUP_TARGET%/}/${stamp}"
mkdir -p "$dest"

copy() {
  local path="$1"
  if [[ -e "$path" ]]; then
    mkdir -p "$dest/$(dirname "$path")"
    tar -C / -cf "$dest/$(basename "$path").tar" "${path#/}"
    echo "saved ${path}"
  fi
}

copy /srv/server/data/caddy
copy /srv/server/data/authentik
copy /srv/server/data/dashboard
copy /srv/server/data/forgejo
copy /srv/bulk/minecraft
copy /srv/bulk/nextcloud
copy /etc/caddy

echo "Backup written to ${dest}"
