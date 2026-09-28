#!/usr/bin/env python3
"""Render Caddy, ntfy, Grafana alerting, and Lavalink config from .env."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"


def load_env(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def profiles() -> list[str]:
    path = ROOT / "config" / "profiles"
    if not path.exists():
        path.write_text((ROOT / "config" / "profiles.default").read_text(encoding="utf-8"), encoding="utf-8")
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        name = line.strip()
        if name and name not in rows:
            rows.append(name)
    if "core" not in rows:
        rows.insert(0, "core")
    return rows


def render_caddy(env: dict[str, str], enabled: set[str]) -> None:
    text = (ROOT / "infrastructure" / "caddy" / "Caddyfile.template").read_text(encoding="utf-8")
    host = env.get("DASHBOARD_HOST", "dashboard.example.com")
    token = env.get("CLOUDFLARE_API_TOKEN", "")
    if host.endswith("example.com"):
        tls = "\ttls internal\n"
    elif token:
        tls = "\ttls {\n\t\tdns cloudflare {env.CLOUDFLARE_API_TOKEN}\n\t}\n"
    else:
        tls = ""
    text = text.replace("##TLS##\n", tls)
    for profile, marker in {
        "media": "MEDIA",
        "git": "GIT",
        "collab": "COLLAB",
        "deploy": "DEPLOY",
    }.items():
        pattern = re.compile(rf"##{marker}##.*?##/{marker}##\n?", re.S)
        if profile in enabled:
            text = text.replace(f"##{marker}##\n", "").replace(f"##/{marker}##\n", "")
        else:
            text = pattern.sub("", text)
    target = RUNTIME / "Caddyfile"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def render_ntfy(env: dict[str, str]) -> None:
    host = env.get("NOTIFY_HOST", "notify.example.com")
    text = f"""base-url: https://{host}
behind-proxy: true
auth-file: /var/lib/ntfy/user.db
auth-default-access: deny-all
attachment-cache-dir: /var/lib/ntfy/attachments
cache-file: /var/lib/ntfy/cache.db
"""
    target = RUNTIME / "ntfy" / "server.yml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def render_grafana(env: dict[str, str]) -> None:
    password = env.get("NTFY_ADMIN_PASSWORD", "")
    contact = f"""apiVersion: 1
contactPoints:
  - orgId: 1
    name: ntfy
    receivers:
      - uid: ntfy-admin
        type: webhook
        settings:
          url: http://ntfyadmin:{password}@server-ntfy/admin
          httpMethod: POST
"""
    policy = """apiVersion: 1
policies:
  - orgId: 1
    receiver: ntfy
    group_by: ["alertname"]
"""
    folder = RUNTIME / "grafana" / "provisioning" / "alerting"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "contactpoints.yml").write_text(contact, encoding="utf-8")
    (folder / "policies.yml").write_text(policy, encoding="utf-8")


def render_lavalink(env: dict[str, str]) -> None:
    password = env.get("LAVALINK_PASSWORD", "change-me")
    text = f"""server:
  port: 2333
  address: 0.0.0.0
lavalink:
  server:
    password: "{password}"
    sources:
      youtube: false
      bandcamp: true
      soundcloud: true
      twitch: false
      vimeo: false
      http: true
      local: false
logging:
  level:
    root: INFO
    lavalink: INFO
"""
    target = RUNTIME / "lavalink" / "application.yml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def render_coolify(env: dict[str, str]) -> None:
    text = "\n".join(
        [
            "APP_NAME=Coolify",
            "APP_ENV=production",
            f"APP_ID={env.get('COOLIFY_APP_ID', '')}",
            f"APP_KEY={env.get('COOLIFY_APP_KEY', '')}",
            f"APP_URL=https://{env.get('APPS_HOST', 'apps.example.com')}",
            "DB_HOST=server-coolify-db",
            "DB_PORT=5432",
            "DB_DATABASE=coolify",
            "DB_USERNAME=coolify",
            f"DB_PASSWORD={env.get('COOLIFY_DB_PASSWORD', '')}",
            "REDIS_HOST=server-coolify-redis",
            "REDIS_PORT=6379",
            f"REDIS_PASSWORD={env.get('COOLIFY_REDIS_PASSWORD', '')}",
            f"PUSHER_APP_ID={env.get('COOLIFY_PUSHER_APP_ID', '')}",
            f"PUSHER_APP_KEY={env.get('COOLIFY_PUSHER_APP_KEY', '')}",
            f"PUSHER_APP_SECRET={env.get('COOLIFY_PUSHER_APP_SECRET', '')}",
            "PUSHER_HOST=server-coolify-realtime",
            "PUSHER_PORT=6001",
            "PUSHER_SCHEME=http",
            "ROOT_USERNAME=admin",
            f"ROOT_USER_EMAIL={env.get('AUTHENTIK_BOOTSTRAP_EMAIL', '')}",
            f"ROOT_USER_PASSWORD={env.get('COOLIFY_ROOT_PASSWORD', '')}",
            "REGISTRY_URL=docker.io",
            "SSL_MODE=off",
            "",
        ]
    )
    RUNTIME.mkdir(parents=True, exist_ok=True)
    (RUNTIME / "coolify.env").write_text(text, encoding="utf-8")
    host = Path("/data/coolify/source")
    try:
        host.mkdir(parents=True, exist_ok=True)
        (host / ".env").write_text(text, encoding="utf-8")
    except OSError:
        return


def main() -> None:
    env = load_env(ROOT / ".env")
    enabled = set(profiles())
    render_caddy(env, enabled)
    render_ntfy(env)
    render_grafana(env)
    render_lavalink(env)
    render_coolify(env)
    print("Rendered runtime config for profiles:", ", ".join(sorted(enabled)))


if __name__ == "__main__":
    main()
