#!/usr/bin/env bash
# Checks the server after repo_setup_guide.md. A phone off home Wi-Fi is still the real public test.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

fail=0
warn=0
ok() { echo "PASS  $*"; }
bad() { echo "FAIL  $*"; fail=$((fail + 1)); }
note() { echo "WARN  $*"; warn=$((warn + 1)); }

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

host="${DASHBOARD_HOST:-dashboard.example.com}"

echo "Local checks"
echo

if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  ok "Docker is running"
else
  bad "Docker is not running"
fi

if tailscale ip -4 >/dev/null 2>&1; then
  ok "Tailscale has an address ($(tailscale ip -4 | head -n 1))"
else
  bad "Tailscale has no IPv4 address"
fi

if sudo ufw status 2>/dev/null | grep -q "Status: active"; then
  ok "UFW is active"
else
  bad "UFW is not active"
fi

ufw_out="$(sudo ufw status verbose 2>/dev/null || true)"
if echo "$ufw_out" | grep -q "80/tcp"; then
  ok "UFW allows 80/tcp"
else
  bad "UFW does not show an allow rule for 80/tcp"
fi
if echo "$ufw_out" | grep -q "443/tcp"; then
  ok "UFW allows 443/tcp"
else
  bad "UFW does not show an allow rule for 443/tcp"
fi
if echo "$ufw_out" | grep -E "22/tcp +ALLOW IN +Anywhere" >/dev/null; then
  bad "SSH is allowed from anywhere. It should be limited to tailscale0"
elif echo "$ufw_out" | grep -q "tailscale0"; then
  ok "SSH is limited to the Tailscale interface"
else
  note "Could not confirm the SSH rule is limited to tailscale0"
fi

if ip -4 addr show | grep -q "192.168.50.10/"; then
  ok "Server address is 192.168.50.10"
elif ip -4 addr show | grep -q "192.168.50."; then
  note "Server is on 192.168.50.0/24 but not .10. Port forwards must use the address ip addr shows"
else
  bad "Server is not on 192.168.50.0/24"
fi

if ping -c 1 -W 2 192.168.1.1 >/dev/null 2>&1; then
  bad "Server reached 192.168.1.1. The VLAN should block the home LAN"
else
  ok "Server did not reach 192.168.1.1"
fi

if [[ -d /srv/bulk/media && -d /srv/server/data ]]; then
  ok "Storage paths exist"
else
  bad "Missing /srv/bulk/media or /srv/server/data. Run scripts/setup.sh"
fi

if [[ ! -f .env ]]; then
  bad ".env is missing"
elif [[ "$host" == *.example.com ]]; then
  note "DASHBOARD_HOST is still example.com, so certificates are internal only"
else
  ok "Dashboard host is ${host}"
fi

for name in server-caddy server-dashboard server-authentik; do
  state="$(docker inspect -f '{{.State.Status}}' "$name" 2>/dev/null || true)"
  if [[ "$state" == "running" ]]; then
    ok "${name} is running"
  else
    bad "${name} is not running (${state:-missing})"
  fi
done

if ss -lnt | grep -q ":80 "; then
  ok "Something is listening on port 80"
else
  bad "Nothing is listening on port 80"
fi
if ss -lnt | grep -q ":443 "; then
  ok "Something is listening on port 443"
else
  bad "Nothing is listening on port 443"
fi

health="$(docker exec server-dashboard python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5).read().decode())" 2>/dev/null || true)"
if echo "$health" | grep -q online; then
  ok "Dashboard /health returns online inside the container"
else
  bad "Dashboard /health did not return online"
fi

if command -v curl >/dev/null 2>&1 && [[ "$host" != *.example.com ]]; then
  edge="$(curl -fsS -k --max-time 10 --resolve "${host}:443:127.0.0.1" "https://${host}/health" 2>/dev/null || true)"
  if echo "$edge" | grep -q '"status":"online"' || echo "$edge" | grep -q '"status": "online"'; then
    ok "Caddy serves https://${host}/health on this machine"
  else
    bad "Caddy did not serve https://${host}/health locally"
  fi
fi

echo
echo "Path from the internet"
echo

if [[ "$host" == *.example.com ]]; then
  note "Skipping public DNS until DASHBOARD_HOST is a real name"
else
  resolved="$(python3 - <<PY
import socket
try:
    print(socket.getaddrinfo("${host}", 443)[0][4][0])
except OSError as exc:
    print("error")
PY
)"
  if [[ "$resolved" == "error" || -z "$resolved" ]]; then
    bad "DNS did not resolve ${host}"
  else
    ok "DNS resolves ${host} to ${resolved}"
  fi

  if command -v curl >/dev/null 2>&1; then
    public="$(curl -4 -fsS --max-time 8 https://cloudflare.com/cdn-cgi/trace 2>/dev/null | awk -F= '/^ip=/{print $2}' || true)"
    if [[ -n "$public" ]]; then
      ok "This network's public IPv4 is ${public}"
      if [[ -n "${resolved:-}" && "$resolved" != "$public" && "$resolved" != "error" ]]; then
        note "DNS points at ${resolved}, which is not this network's public IP ${public}. Proxied Cloudflare names often look like that. Confirm the A record targets ${public}"
      fi
    else
      note "Could not read the public IP from Cloudflare"
    fi
    outside="$(curl -fsS --max-time 15 "https://${host}/health" 2>/dev/null || true)"
    if echo "$outside" | grep -q online; then
      ok "https://${host}/health answered from this server"
    else
      note "https://${host}/health did not answer from inside the house. Home routers often cannot hairpin. Test from a phone on cellular data"
    fi
  fi
fi

echo
echo "From a phone on cellular, not home Wi-Fi:"
echo "  open https://${host}/health and expect {\"status\":\"online\"}"
echo "  open https://${host} and sign in"
echo "  confirm http://${host} redirects to https"
echo "  ssh to the public IP should fail"
echo
echo "${fail} failed, ${warn} warnings"
if [[ "$fail" -gt 0 ]]; then
  exit 1
fi
