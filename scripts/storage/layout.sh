#!/usr/bin/env bash
# Lay out the OS disk and one or more bulk disks.
# Ubuntu stays on the disk that holds /. Everything large goes to the other disks.
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this as root: sudo bash scripts/storage/layout.sh"
  exit 1
fi

FORMAT_DISK=""
FORMAT_BULK=0
ALLOW_SINGLE=0
for arg in "$@"; do
  case "$arg" in
    --format-bulk) FORMAT_BULK=1 ;;
    --allow-single-disk) ALLOW_SINGLE=1 ;;
    --format)
      echo "Use: --format /dev/disk/by-id/..."
      exit 1
      ;;
    --format=*) FORMAT_DISK="${arg#--format=}" ;;
    /dev/*) FORMAT_DISK="$arg" ;;
  esac
done

os_source="$(findmnt -n -o SOURCE /)"
os_parent="$(lsblk -no PKNAME "$os_source" 2>/dev/null || true)"
if [[ -z "$os_parent" ]]; then
  os_disk="/dev/$(basename "$os_source")"
else
  os_disk="/dev/${os_parent}"
fi

echo "Operating system disk: ${os_disk} ($(lsblk -no MODEL,SIZE "$os_disk" | tr -s ' '))"
echo "Other disks:"
lsblk -dn -o NAME,SIZE,TYPE,MODEL,TRAN | sed 's/^/  /'

candidates=()
while read -r name _; do
  [[ -z "$name" ]] && continue
  device="/dev/${name}"
  [[ "$device" == "$os_disk" ]] && continue
  size="$(lsblk -bno SIZE "$device")"
  if [[ "${size:-0}" -lt 100000000000 ]]; then
    continue
  fi
  candidates+=("$device")
done < <(lsblk -dn -o NAME,TYPE | awk '$2=="disk" {print $1}')

partition_count() {
  lsblk -n -o TYPE "$1" | grep -c part || true
}

label_of() {
  lsblk -no LABEL "$1" 2>/dev/null | awk 'NF {print; exit}'
}

if [[ "$FORMAT_BULK" -eq 1 && -z "$FORMAT_DISK" ]]; then
  if [[ "${#candidates[@]}" -ne 1 ]]; then
    echo "Expected one non-OS disk to format. Found ${#candidates[@]}."
    echo "Pass it explicitly: sudo bash scripts/storage/layout.sh --format /dev/disk/by-id/..."
    printf '  %s\n' "${candidates[@]:-none}"
    exit 1
  fi
  FORMAT_DISK="${candidates[0]}"
fi

if [[ -n "$FORMAT_DISK" ]]; then
  if [[ "$(readlink -f "$FORMAT_DISK")" == "$(readlink -f "$os_disk")" ]]; then
    echo "Refusing to format the operating system disk."
    exit 1
  fi
  parts="$(partition_count "$FORMAT_DISK")"
  if [[ "$parts" -gt 0 ]]; then
    echo "${FORMAT_DISK} already has partitions. Not formatting it."
    echo "If this disk should become bulk storage, wipe it yourself only when you are sure it is empty, then run this again."
    exit 1
  fi
  existing="$(lsblk -ln -o LABEL | grep -c '^server-bulk' || true)"
  if [[ "${existing}" -eq 0 ]]; then
    new_label="server-bulk"
  else
    new_label="server-bulk$((existing + 1))"
  fi
  echo "Formatting ${FORMAT_DISK} as ext4 with label ${new_label}"
  parted -s "$FORMAT_DISK" mklabel gpt
  parted -s "$FORMAT_DISK" mkpart primary ext4 1MiB 100%
  udevadm settle
  part="$(lsblk -ln -o PATH,TYPE "$FORMAT_DISK" | awk '$2=="part" {print $1; exit}')"
  if [[ -z "$part" ]]; then
    echo "Could not find the new partition on ${FORMAT_DISK}"
    exit 1
  fi
  mkfs.ext4 -F -L "$new_label" "$part"
  udevadm settle
fi

mapfile -t labeled < <(lsblk -ln -o PATH,LABEL,TYPE | awk '$3=="part" && $2 ~ /^server-bulk/ {print $1" "$2}')

if [[ "${#labeled[@]}" -eq 0 ]]; then
  if [[ "$ALLOW_SINGLE" -eq 1 || "$FORMAT_BULK" -eq 0 ]]; then
    echo "No bulk disk is mounted. Using ${os_disk} for /srv/bulk until you add the bay SSD."
    echo "When the second disk is ready: sudo bash scripts/storage/add-disk.sh /dev/disk/by-id/..."
    mkdir -p /srv/server/on-os-disk
    if [[ -L /srv/bulk || ! -e /srv/bulk ]]; then
      ln -sfn /srv/server/on-os-disk /srv/bulk
    fi
  else
    echo "No disk labeled server-bulk was found."
    exit 1
  fi
else
  apt-get update
  apt-get install -y mergerfs
  if [[ -f /etc/fuse.conf ]] && ! grep -q '^user_allow_other' /etc/fuse.conf; then
    echo "user_allow_other" >> /etc/fuse.conf
  fi
  mkdir -p /mnt/disks
  branches=()
  fstab_lines=()
  for row in "${labeled[@]}"; do
    part="${row%% *}"
    label="${row##* }"
    mkdir -p "/mnt/disks/${label}"
    fstab_lines+=("UUID=$(blkid -s UUID -o value "$part") /mnt/disks/${label} ext4 defaults,noatime 0 2")
    if ! mountpoint -q "/mnt/disks/${label}"; then
      mount "/mnt/disks/${label}" 2>/dev/null || mount "$part" "/mnt/disks/${label}"
    fi
    branches+=("/mnt/disks/${label}")
  done
  joined="$(IFS=:; echo "${branches[*]}")"
  fstab_lines+=("${joined} /srv/bulk fuse.mergerfs defaults,allow_other,use_ino,category.create=mfs,moveonenospc=true,minfreespace=50G,fsname=server-bulk 0 0")
  block="$(mktemp)"
  {
    echo "# BEGIN the-server-storage"
    printf '%s\n' "${fstab_lines[@]}"
    echo "# END the-server-storage"
  } > "$block"
  python3 - "$block" <<'PY'
import sys
from pathlib import Path
block = Path(sys.argv[1]).read_text()
path = Path("/etc/fstab")
text = path.read_text() if path.exists() else ""
begin = "# BEGIN the-server-storage"
end = "# END the-server-storage"
if begin in text and end in text:
    pre, rest = text.split(begin, 1)
    _, post = rest.split(end, 1)
    path.write_text(pre + block + post.lstrip("\n"))
else:
    if text and not text.endswith("\n"):
        text += "\n"
    path.write_text(text + block)
PY
  rm -f "$block"
  mkdir -p /srv/bulk
  if mountpoint -q /srv/bulk; then
    umount /srv/bulk || true
  fi
  if [[ -L /srv/bulk ]]; then
    rm -f /srv/bulk
    mkdir -p /srv/bulk
  fi
  mount /srv/bulk || mount -t fuse.mergerfs -o defaults,allow_other,use_ino,category.create=mfs,moveonenospc=true,minfreespace=50G,fsname=server-bulk "$joined" /srv/bulk
fi

mkdir -p \
  /srv/bulk/media/{Movies,TV,Music,Photos,Other} \
  /srv/bulk/models \
  /srv/bulk/backups \
  /srv/bulk/storage/{downloads,games,software,projects,releases} \
  /srv/bulk/lancache \
  /srv/bulk/minecraft \
  /srv/bulk/nextcloud

link_into_server() {
  local name="$1"
  local source="/srv/bulk/${name}"
  local dest="/srv/server/${name}"
  mkdir -p /srv/server
  if [[ -L "$dest" ]]; then
    ln -sfn "$source" "$dest"
    return
  fi
  if [[ -d "$dest" ]]; then
    if [[ -z "$(ls -A "$dest")" ]]; then
      rmdir "$dest"
      ln -sfn "$source" "$dest"
    else
      echo "${dest} already has files. Left it in place."
    fi
    return
  fi
  ln -sfn "$source" "$dest"
}

link_into_server media
link_into_server models
link_into_server backups
link_into_server storage

echo "Storage is ready."
findmnt -n -o SOURCE,TARGET,FSTYPE / /srv/bulk || true
df -h / /srv/bulk || true
