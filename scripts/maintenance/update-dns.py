#!/usr/bin/env python3
"""Point this server's Cloudflare A records at the current public address."""

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

INTERVAL = 300
API = "https://api.cloudflare.com/client/v4"


def env(name: str) -> str:
    return os.environ.get(name, "").strip()


def public_ip() -> str:
    request = urllib.request.Request("https://1.1.1.1/cdn-cgi/trace", headers={"User-Agent": "the-server-dns"})
    with urllib.request.urlopen(request, timeout=20) as response:
        text = response.read().decode()
    for line in text.splitlines():
        if line.startswith("ip="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("Cloudflare trace did not include an address")


def api(token: str, method: str, path: str, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        API + path,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode())
    if not payload.get("success", False):
        raise RuntimeError(str(payload.get("errors")))
    return payload


def hosts() -> list[str]:
    domain = env("DOMAIN")
    names = []
    for key, value in os.environ.items():
        if not key.endswith("_HOST"):
            continue
        name = value.strip()
        if name and (name == domain or name.endswith("." + domain)):
            names.append(name)
    return sorted(set(names))


def update_once() -> None:
    token = env("CLOUDFLARE_API_TOKEN")
    domain = env("DOMAIN")
    if not token or not domain or domain.endswith("example.com"):
        print("DNS updater waiting for a real domain and CLOUDFLARE_API_TOKEN.")
        return
    address = public_ip()
    zone_name = urllib.parse.quote(domain)
    zones = api(token, "GET", f"/zones?name={zone_name}")
    result = zones.get("result") or []
    if not result:
        print(f"No Cloudflare zone named {domain}.")
        return
    zone_id = result[0]["id"]
    for name in hosts():
        listed = api(token, "GET", f"/zones/{zone_id}/dns_records?type=A&name={urllib.parse.quote(name)}")
        records = listed.get("result") or []
        if not records:
            print(f"No A record for {name}. Create it in Cloudflare first.")
            continue
        record = records[0]
        if record.get("content") == address and record.get("proxied") is True:
            continue
        api(
            token,
            "PUT",
            f"/zones/{zone_id}/dns_records/{record['id']}",
            {"type": "A", "name": name, "content": address, "proxied": True, "ttl": 1},
        )
        print(f"Updated {name} to {address}.")


def main() -> None:
    while True:
        try:
            update_once()
        except (OSError, urllib.error.URLError, json.JSONDecodeError, TimeoutError, RuntimeError) as exc:
            print(f"DNS update failed: {exc}")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
