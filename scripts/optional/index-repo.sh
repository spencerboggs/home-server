#!/usr/bin/env bash
# Build a Codegraph index for one repository.
# Refuses to run when a secret file is present and not gitignored.
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: sudo bash scripts/optional/index-repo.sh /path/to/repo"
  exit 1
fi

if ! command -v codegraph >/dev/null 2>&1; then
  echo "Run sudo bash scripts/optional/install-codegraph.sh first."
  exit 1
fi

target="$(readlink -f "$1")"
if [[ ! -d "$target" ]]; then
  echo "Not a directory: ${target}"
  exit 1
fi

python3 - "$target" <<'PY'
import os
import subprocess
import sys

root = sys.argv[1]
exact = {".env", ".env.local", "id_rsa", "id_ed25519", "credentials.json"}
suffixes = (".pem", ".key")
bad = []
git = os.path.isdir(os.path.join(root, ".git"))
for dirpath, dirnames, filenames in os.walk(root):
    dirnames[:] = [name for name in dirnames if name not in {".git", "node_modules", ".codegraph"}]
    for name in filenames:
        if name not in exact and not name.endswith(suffixes):
            continue
        full = os.path.join(dirpath, name)
        rel = os.path.relpath(full, root)
        ignored = False
        if git:
            check = subprocess.run(["git", "-C", root, "check-ignore", "-q", "--", rel], check=False)
            ignored = check.returncode == 0
        if not ignored:
            bad.append(rel)
if bad:
    print("Refusing to index. These files are not gitignored:")
    print("\n".join(bad))
    raise SystemExit(1)
PY

codegraph index "$target"
