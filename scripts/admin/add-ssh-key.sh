#!/usr/bin/env bash
# Give a programmer an SSH login that works from any network over Tailscale.
# Does not open port 22 on the public internet.
#
# Usage:
#   sudo bash scripts/admin/add-ssh-key.sh alice "ssh-ed25519 AAAA... alice@laptop"
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run: sudo bash scripts/admin/add-ssh-key.sh USER KEY"
  exit 1
fi

if [[ $# -ne 2 ]]; then
  echo "Usage: sudo bash scripts/admin/add-ssh-key.sh USER \"ssh-ed25519 AAAA... comment\""
  exit 1
fi

user="$1"
key="$2"

if [[ ! "$user" =~ ^[a-z][a-z0-9-]{0,31}$ ]]; then
  echo "Username must be lowercase letters, digits, or hyphens."
  exit 1
fi

case "$key" in
  ssh-ed25519\ *|ssh-rsa\ *|ecdsa-sha2-nistp256\ *) ;;
  *)
    echo "Key must start with ssh-ed25519, ssh-rsa, or ecdsa-sha2-nistp256."
    exit 1
    ;;
esac

if ! id "$user" >/dev/null 2>&1; then
  adduser --disabled-password --gecos "" "$user"
fi

usermod -aG sudo,docker "$user"
install -d -m 700 -o "$user" -g "$user" "/home/${user}/.ssh"
auth="/home/${user}/.ssh/authorized_keys"
touch "$auth"
if ! grep -qxF "$key" "$auth"; then
  printf '%s\n' "$key" >> "$auth"
fi
chown "$user:$user" "$auth"
chmod 600 "$auth"

echo "Added ${user}. They install Tailscale, join this tailnet, then:"
echo "  ssh ${user}@$(tailscale ip -4 2>/dev/null | head -n 1 || echo 100.x.x.x)"
echo "Port 22 stays closed on the public internet."
