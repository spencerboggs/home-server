#!/usr/bin/env bash
# Put akadmin in the administrators group and create the ntfy admin user.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

set -a
# shellcheck disable=SC1091
source .env
set +a

echo "Waiting for Authentik..."
ready=0
for _ in $(seq 1 40); do
  if docker exec server-authentik ak healthcheck >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 5
done

if [[ "$ready" -ne 1 ]]; then
  echo "Authentik did not become ready."
  exit 1
fi

py="python"
if ! docker exec server-authentik python -c "print(1)" >/dev/null 2>&1; then
  py="python3"
fi

docker exec -i \
  -e AUTHENTIK_BOOTSTRAP_TOKEN="${AUTHENTIK_BOOTSTRAP_TOKEN}" \
  server-authentik "$py" - <<'PY'
import json
import os
import urllib.error
import urllib.request

token = os.environ.get("AUTHENTIK_BOOTSTRAP_TOKEN", "")
base = "http://127.0.0.1:9000"

def call(method, path, body=None):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        base + path,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read().decode()
        return json.loads(raw) if raw else {}

try:
    users = call("GET", "/api/v3/core/users/?search=akadmin")
    groups = call("GET", "/api/v3/core/groups/?name=administrators")
except urllib.error.HTTPError as exc:
    print(exc.read().decode()[:400])
    raise SystemExit("Could not use the Authentik API token. Sign in as akadmin and confirm the administrators group exists.")

admin = next((item for item in users.get("results", []) if item.get("username") == "akadmin"), None)
group = next((item for item in groups.get("results", []) if item.get("name") == "administrators"), None)
if admin and group:
    call("POST", f"/api/v3/core/groups/{group['pk']}/add_user/", {"pk": admin["pk"]})
    print("akadmin is in the administrators group.")
else:
    print("akadmin or the administrators group was not found yet. Open Authentik and check the blueprint logs.")
PY

if docker ps --format '{{.Names}}' | grep -qx server-ntfy; then
  docker exec -i server-ntfy ntfy user add --role=admin ntfyadmin <<EOF || true
${NTFY_ADMIN_PASSWORD}
${NTFY_ADMIN_PASSWORD}
EOF
  docker exec server-ntfy ntfy access ntfyadmin "*" read-write || true
  docker exec server-ntfy ntfy access "*" general read || true
  echo "ntfy admin user is ntfyadmin. The password is NTFY_ADMIN_PASSWORD in .env."
fi
