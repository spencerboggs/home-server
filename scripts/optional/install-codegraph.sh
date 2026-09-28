#!/usr/bin/env bash
# Install the Codegraph Linux bundle from its GitHub release.
# The index is for repository structure. Do not point it at secret files.
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run: sudo bash scripts/optional/install-codegraph.sh"
  exit 1
fi

arch="$(uname -m)"
case "$arch" in
  x86_64) asset="codegraph-linux-x64.tar.gz" ;;
  aarch64|arm64) asset="codegraph-linux-arm64.tar.gz" ;;
  *)
    echo "No Codegraph bundle for ${arch}."
    exit 1
    ;;
esac

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
api="https://api.github.com/repos/colbymchenry/codegraph/releases/latest"

echo "Looking up the latest Codegraph release"
curl -fsSL "$api" -o "$tmp/release.json"
python3 - "$tmp/release.json" "$asset" "$tmp" <<'PY'
import json
import sys
import urllib.request
from pathlib import Path

release = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
wanted = sys.argv[2]
dest = Path(sys.argv[3])
assets = {item["name"]: item["browser_download_url"] for item in release.get("assets", [])}
if wanted not in assets or "SHA256SUMS" not in assets:
    raise SystemExit(f"Release is missing {wanted} or SHA256SUMS")
for name in (wanted, "SHA256SUMS"):
    urllib.request.urlretrieve(assets[name], dest / name)
print(release.get("tag_name", "unknown"))
PY

(
  cd "$tmp"
  grep " ${asset}$" SHA256SUMS | sha256sum -c -
)

rm -rf /opt/codegraph
mkdir -p /opt/codegraph
tar -xzf "$tmp/$asset" -C /opt/codegraph
launcher="$(find /opt/codegraph -type f -path '*/bin/codegraph' | head -n 1)"
if [[ -z "$launcher" ]]; then
  echo "The archive did not contain bin/codegraph."
  exit 1
fi
chmod 755 "$launcher"
ln -sfn "$launcher" /usr/local/bin/codegraph
echo "Installed ${launcher}"
echo "Index a repository with: sudo bash scripts/optional/index-repo.sh /path/to/repo"
