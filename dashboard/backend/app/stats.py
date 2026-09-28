import json
import urllib.error
import urllib.parse
import urllib.request

from .config import PROMETHEUS_URL


def _query(expression: str) -> float | None:
    url = f"{PROMETHEUS_URL}/api/v1/query?{urllib.parse.urlencode({'query': expression})}"
    try:
        with urllib.request.urlopen(url, timeout=4) as response:
            payload = json.loads(response.read().decode())
    except (OSError, urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        return None
    result = payload.get("data", {}).get("result", [])
    if not result:
        return None
    try:
        return float(result[0]["value"][1])
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def _round(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 1)


def stats() -> dict:
    cpu = _query('100 * (1 - avg(rate(node_cpu_seconds_total{mode="idle"}[2m])))')
    ram = _query("100 * (1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes))")
    root = _query(
        '100 * (1 - (node_filesystem_avail_bytes{mountpoint="/",fstype!~"tmpfs|overlay"} / node_filesystem_size_bytes{mountpoint="/",fstype!~"tmpfs|overlay"}))'
    )
    bulk = _query(
        '100 * (1 - (node_filesystem_avail_bytes{mountpoint="/srv/bulk",fstype!~"tmpfs|overlay"} / node_filesystem_size_bytes{mountpoint="/srv/bulk",fstype!~"tmpfs|overlay"}))'
    )
    gpu = _query("avg(DCGM_FI_DEV_GPU_UTIL)")
    power = _query("sum(node_hwmon_power_average_watt)")
    storage = bulk if bulk is not None else root
    return {
        "cpu": _round(cpu),
        "ram": _round(ram),
        "gpu": _round(gpu),
        "storage": _round(storage),
        "root_disk": _round(root),
        "bulk_disk": _round(bulk),
        "power": _round(power),
    }


def processes() -> list[dict]:
    mem_q = 'container_memory_working_set_bytes{id=~"/docker/.+"}'
    cpu_q = 'rate(container_cpu_usage_seconds_total{id=~"/docker/.+"}[2m])'
    mem = _vector(mem_q)
    cpu = _vector(cpu_q)
    rows = []
    for item_id, item in mem.items():
        name = item.get("name") or item.get("container_label_com_docker_compose_service") or item_id
        if name in {"", "POD"}:
            continue
        rows.append(
            {
                "name": name.removeprefix("/"),
                "cpu": round((cpu.get(item_id, {}).get("value") or 0) * 100, 1),
                "ram_bytes": int(item.get("value") or 0),
                "gpu": None,
            }
        )
    rows.sort(key=lambda row: row["ram_bytes"], reverse=True)
    return rows[:40]


def _vector(expression: str) -> dict:
    url = f"{PROMETHEUS_URL}/api/v1/query?{urllib.parse.urlencode({'query': expression})}"
    try:
        with urllib.request.urlopen(url, timeout=4) as response:
            payload = json.loads(response.read().decode())
    except (OSError, urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        return {}
    found = {}
    for item in payload.get("data", {}).get("result", []):
        metric = item.get("metric", {})
        item_id = metric.get("id") or metric.get("name") or ""
        try:
            value = float(item["value"][1])
        except (KeyError, IndexError, TypeError, ValueError):
            continue
        found[item_id] = {**metric, "value": value}
    return found
