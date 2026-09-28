#!/usr/bin/env bash
# Add another bulk disk to the mergerfs pool. The disk must not be the OS disk.
set -euo pipefail
if [[ $# -ne 1 ]]; then
  echo "Usage: sudo bash scripts/storage/add-disk.sh /dev/disk/by-id/ata-..."
  exit 1
fi
exec bash "$(dirname "$0")/layout.sh" "$1"
