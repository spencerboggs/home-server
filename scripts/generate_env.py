#!/usr/bin/env python3
"""Fill .env secrets without touching values that are already set."""

import base64
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / ".env.example"
TARGET = ROOT / ".env"

GENERATED = {
    "AUTHENTIK_SECRET_KEY": lambda: secrets.token_urlsafe(48),
    "AUTHENTIK_BOOTSTRAP_PASSWORD": lambda: secrets.token_hex(18),
    "AUTHENTIK_BOOTSTRAP_TOKEN": lambda: secrets.token_hex(24),
    "PG_PASS": lambda: secrets.token_hex(18),
    "DASHBOARD_OIDC_SECRET": lambda: secrets.token_hex(24),
    "EXECUTOR_TOKEN": lambda: secrets.token_hex(24),
    "REDIS_PASSWORD": lambda: secrets.token_hex(18),
    "GRAFANA_ADMIN_PASSWORD": lambda: secrets.token_hex(18),
    "GRAFANA_OIDC_SECRET": lambda: secrets.token_hex(24),
    "FORGEJO_OIDC_SECRET": lambda: secrets.token_hex(24),
    "NEXTCLOUD_OIDC_SECRET": lambda: secrets.token_hex(24),
    "JELLYFIN_OIDC_SECRET": lambda: secrets.token_hex(24),
    "FORGEJO_DB_PASSWORD": lambda: secrets.token_hex(18),
    "NEXTCLOUD_DB_PASSWORD": lambda: secrets.token_hex(18),
    "NEXTCLOUD_ADMIN_PASSWORD": lambda: secrets.token_hex(18),
    "NTFY_ADMIN_PASSWORD": lambda: secrets.token_hex(18),
    "MINECRAFT_RCON_PASSWORD": lambda: secrets.token_hex(12),
    "LAVALINK_PASSWORD": lambda: secrets.token_hex(18),
    "COOLIFY_DB_PASSWORD": lambda: secrets.token_hex(18),
    "COOLIFY_REDIS_PASSWORD": lambda: secrets.token_hex(18),
    "COOLIFY_APP_KEY": lambda: "base64:" + base64.b64encode(secrets.token_bytes(32)).decode(),
    "COOLIFY_APP_ID": lambda: secrets.token_hex(16),
    "COOLIFY_ROOT_PASSWORD": lambda: secrets.token_hex(18),
    "COOLIFY_PUSHER_APP_ID": lambda: secrets.token_hex(16),
    "COOLIFY_PUSHER_APP_KEY": lambda: secrets.token_hex(16),
    "COOLIFY_PUSHER_APP_SECRET": lambda: secrets.token_hex(16),
}


def main() -> None:
    example_lines = EXAMPLE.read_text(encoding="utf-8").splitlines()
    if TARGET.exists():
        lines = TARGET.read_text(encoding="utf-8").splitlines()
    else:
        lines = list(example_lines)
    present = set()
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in line:
            present.add(line.split("=", 1)[0])
    for line in example_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            continue
        key = line.split("=", 1)[0]
        if key not in present:
            lines.append(line)
            present.add(key)
    output = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            output.append(line)
            continue
        key, value = line.split("=", 1)
        if key in GENERATED and not value.strip():
            output.append(f"{key}={GENERATED[key]()}")
        else:
            output.append(line)
    TARGET.write_text("\n".join(output) + "\n", encoding="utf-8")
    print(f"Wrote {TARGET}")


if __name__ == "__main__":
    main()
