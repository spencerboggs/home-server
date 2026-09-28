#!/usr/bin/env bash
# Connect Forgejo, Nextcloud, and Jellyfin to the Authentik applications
# created by the blueprint. Safe to run more than once.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

running() {
  docker ps --format '{{.Names}}' | grep -qx "$1"
}

if running server-forgejo; then
  echo "Configuring Forgejo SSO"
  ready=0
  for _ in $(seq 1 30); do
    if docker exec -u git server-forgejo forgejo admin auth list >/dev/null 2>&1; then
      ready=1
      break
    fi
    sleep 5
  done
  if [[ "$ready" -eq 1 ]]; then
    if docker exec -u git server-forgejo forgejo admin auth list | grep -q 'Authentik'; then
      echo "Forgejo already has the Authentik login."
    else
      docker exec -u git \
        -e FORGEJO_OIDC_SECRET="${FORGEJO_OIDC_SECRET}" \
        -e AUTH_HOST="${AUTH_HOST}" \
        server-forgejo \
        forgejo admin auth add-oauth \
          --name Authentik \
          --provider openidConnect \
          --key forgejo \
          --secret "${FORGEJO_OIDC_SECRET}" \
          --auto-discover-url "https://${AUTH_HOST}/application/o/forgejo/.well-known/openid-configuration" \
          --scopes "openid email profile groups"
    fi
  else
    echo "Forgejo was not ready for SSO. Run sudo bash scripts/configure-sso.sh again after it finishes starting."
  fi
fi

if running server-nextcloud; then
  echo "Configuring Nextcloud SSO"
  ready=0
  for _ in $(seq 1 36); do
    if docker exec -u www-data server-nextcloud php occ status >/dev/null 2>&1; then
      ready=1
      break
    fi
    sleep 5
  done
  if [[ "$ready" -eq 1 ]]; then
    docker exec -u www-data server-nextcloud php occ app:install user_oidc >/dev/null 2>&1 || true
    docker exec -u www-data server-nextcloud php occ app:enable user_oidc >/dev/null 2>&1 || true
    if docker exec -u www-data server-nextcloud php occ user_oidc:provider 2>/dev/null | grep -q 'Authentik'; then
      echo "Nextcloud already has the Authentik login."
    else
      docker exec -u www-data \
        server-nextcloud php occ user_oidc:provider Authentik \
          --clientid=nextcloud \
          --clientsecret="${NEXTCLOUD_OIDC_SECRET}" \
          --discoveryuri="https://${AUTH_HOST}/application/o/nextcloud/.well-known/openid-configuration" \
          --scope="openid email profile groups"
    fi
  else
    echo "Nextcloud was not ready for SSO. Run sudo bash scripts/configure-sso.sh again after the first install finishes."
  fi
fi

if running server-jellyfin; then
  plugin_dir="/srv/server/data/jellyfin/config/plugins/SSO-Auth"
  config_dir="/srv/server/data/jellyfin/config/plugins/configurations"
  marker="${plugin_dir}/.installed"
  if [[ ! -f "$marker" ]]; then
    echo "Downloading the Jellyfin SSO plugin"
    mkdir -p "$plugin_dir" "$config_dir"
    tmp="$(mktemp -d)"
    python3 - "$tmp" "$plugin_dir" <<'PY'
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

tmp = Path(sys.argv[1])
dest = Path(sys.argv[2])
with urllib.request.urlopen(
    "https://api.github.com/repos/9p4/jellyfin-plugin-sso/releases/latest",
    timeout=60,
) as response:
    release = json.loads(response.read().decode())
asset = next(item for item in release.get("assets", []) if str(item.get("name", "")).endswith(".zip"))
archive = tmp / asset["name"]
urllib.request.urlretrieve(asset["browser_download_url"], archive)
with zipfile.ZipFile(archive) as bundle:
    bundle.extractall(dest)
print(asset["name"])
PY
    touch "$marker"
  fi
  config_file="${config_dir}/SSO-Auth.xml"
  if [[ ! -f "$config_file" ]]; then
    cat > "$config_file" <<EOF
<?xml version="1.0" encoding="utf-8"?>
<PluginConfiguration xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">
  <SamlConfigs />
  <OidConfigs>
    <item>
      <key>
        <string>authentik</string>
      </key>
      <value>
        <OidEndpoint>https://${AUTH_HOST}/application/o/jellyfin/.well-known/openid-configuration</OidEndpoint>
        <OidClientId>jellyfin</OidClientId>
        <OidSecret>${JELLYFIN_OIDC_SECRET}</OidSecret>
        <Enabled>true</Enabled>
        <EnableAuthorization>false</EnableAuthorization>
        <EnableAllFolders>true</EnableAllFolders>
        <AdminRoles>
          <string>administrators</string>
        </AdminRoles>
        <Roles />
        <EnableFolderRoles>false</EnableFolderRoles>
        <EnableLiveTvRoles>false</EnableLiveTvRoles>
        <EnableLiveTv>true</EnableLiveTv>
        <EnableLiveTvManagement>false</EnableLiveTvManagement>
        <RoleClaim>groups</RoleClaim>
        <OidScopes>
          <string>openid</string>
          <string>profile</string>
          <string>email</string>
          <string>groups</string>
        </OidScopes>
        <DefaultProvider>authentik</DefaultProvider>
        <NewPath>true</NewPath>
        <SchemeOverride>https</SchemeOverride>
        <DefaultUsernameClaim>preferred_username</DefaultUsernameClaim>
        <DisableHttps>false</DisableHttps>
        <DisablePushedAuthorization>true</DisablePushedAuthorization>
      </value>
    </item>
  </OidConfigs>
</PluginConfiguration>
EOF
    echo "Restarting Jellyfin so it loads the SSO plugin."
    docker restart server-jellyfin >/dev/null
  fi
fi

echo "SSO configuration finished."
