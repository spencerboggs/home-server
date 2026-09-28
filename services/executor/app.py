import hmac
import json
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os

TOKEN = os.environ.get("EXECUTOR_TOKEN", "")
SOCKET_PATH = "/var/run/docker.sock"
MINECRAFT = "server-minecraft"


def docker(method: str, path: str) -> tuple[int, bytes]:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(30)
    try:
        sock.connect(SOCKET_PATH)
        request = (
            f"{method} {path} HTTP/1.0\r\n"
            "Host: docker\r\n"
            "Content-Length: 0\r\n"
            "Connection: close\r\n\r\n"
        )
        sock.sendall(request.encode())
        chunks = []
        while True:
            piece = sock.recv(65536)
            if not piece:
                break
            chunks.append(piece)
    finally:
        sock.close()
    raw = b"".join(chunks)
    header, _, body = raw.partition(b"\r\n\r\n")
    status_line = header.split(b"\r\n", 1)[0]
    parts = status_line.split()
    status = int(parts[1]) if len(parts) > 1 else 500
    return status, body


def decode_logs(body: bytes) -> str:
    pieces = []
    index = 0
    while index + 8 <= len(body):
        stream = body[index]
        if stream not in (0, 1, 2):
            return body.decode(errors="replace")
        size = int.from_bytes(body[index + 4 : index + 8], "big")
        index += 8
        pieces.append(body[index : index + size])
        index += size
        if size == 0:
            break
    if not pieces:
        return body.decode(errors="replace")
    return b"".join(pieces).decode(errors="replace")


def containers() -> list[dict]:
    status, body = docker("GET", "/v1.43/containers/json?all=1")
    if status >= 300:
        return []
    rows = []
    for item in json.loads(body.decode()):
        names = item.get("Names") or ["/unknown"]
        rows.append(
            {
                "name": str(names[0]).lstrip("/"),
                "state": item.get("State") or "unknown",
                "status": item.get("Status") or "",
                "ai": (item.get("Labels") or {}).get("ai-model") == "true",
            }
        )
    return rows


def stop_models() -> dict:
    stopped = []
    for item in containers():
        if item["ai"] and item["state"] == "running":
            code, _ = docker("POST", f"/v1.43/containers/{item['name']}/stop?t=10")
            if code < 300:
                stopped.append(item["name"])
    return {"stopped": stopped}


def rcon(command: str) -> tuple[int, str]:
    import struct

    password = os.environ.get("MINECRAFT_RCON_PASSWORD", "")
    if not password:
        return 503, "MINECRAFT_RCON_PASSWORD is empty"
    try:
        sock = socket.create_connection(("server-minecraft", 25575), timeout=3)
    except OSError as exc:
        return 409, f"Minecraft is not accepting admin commands: {exc}"
    sock.settimeout(3)

    def packet(request_id: int, kind: int, payload: str) -> bytes:
        body = struct.pack("<ii", request_id, kind) + payload.encode() + b"\x00\x00"
        return struct.pack("<i", len(body)) + body

    def read_packet() -> tuple[int, int, str]:
        raw_len = sock.recv(4)
        if len(raw_len) < 4:
            raise OSError("short rcon header")
        length = struct.unpack("<i", raw_len)[0]
        data = b""
        while len(data) < length:
            piece = sock.recv(length - len(data))
            if not piece:
                break
            data += piece
        request_id, kind = struct.unpack("<ii", data[:8])
        return request_id, kind, data[8:-2].decode(errors="replace")

    try:
        sock.sendall(packet(1, 3, password))
        request_id, _, _ = read_packet()
        if request_id == -1:
            return 401, "Minecraft refused the admin password"
        sock.sendall(packet(2, 2, command))
        _, _, text = read_packet()
        return 200, text
    except (OSError, TimeoutError) as exc:
        return 502, str(exc)
    finally:
        sock.close()


def minecraft_status() -> tuple[int, dict]:
    code, text = rcon("list")
    if code != 200:
        return 200, {"online": False, "detail": text, "players": "", "version": ""}
    version_code, version = rcon("version")
    return 200, {
        "online": True,
        "players": text.strip(),
        "version": version.strip() if version_code == 200 else "",
        "detail": "",
    }


def minecraft_backup() -> tuple[int, dict]:
    from datetime import datetime, timezone
    from pathlib import Path

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    folder = Path("/backups")
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / f"minecraft-{stamp}.tar"
    status, size, error = stream_to_file(
        "GET",
        f"/v1.43/containers/{MINECRAFT}/archive?path=/data",
        dest,
    )
    if status == 404:
        dest.unlink(missing_ok=True)
        return 409, {"ok": False, "error": "Minecraft is not created yet. Enable the games profile first."}
    if status >= 300:
        dest.unlink(missing_ok=True)
        return 502, {"ok": False, "error": error[:300]}
    return 200, {"ok": True, "file": str(dest), "bytes": size}


def stream_to_file(method: str, path: str, dest) -> tuple[int, int, str]:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(600)
    try:
        sock.connect(SOCKET_PATH)
        request = (
            f"{method} {path} HTTP/1.0\r\n"
            "Host: docker\r\n"
            "Connection: close\r\n\r\n"
        )
        sock.sendall(request.encode())
        buffer = b""
        while b"\r\n\r\n" not in buffer:
            piece = sock.recv(65536)
            if not piece:
                return 502, 0, "Docker closed the archive request"
            buffer += piece
            if len(buffer) > 1_000_000:
                return 502, 0, "Docker archive headers were too large"
        header, _, rest = buffer.partition(b"\r\n\r\n")
        status_line = header.split(b"\r\n", 1)[0]
        parts = status_line.split()
        status = int(parts[1]) if len(parts) > 1 else 500
        if status >= 300:
            error = rest
            while True:
                piece = sock.recv(65536)
                if not piece:
                    break
                error += piece
            return status, 0, error.decode(errors="replace")
        written = 0
        with dest.open("wb") as handle:
            if rest:
                handle.write(rest)
                written += len(rest)
            while True:
                piece = sock.recv(1024 * 1024)
                if not piece:
                    break
                handle.write(piece)
                written += len(piece)
        return status, written, ""
    except (OSError, TimeoutError) as exc:
        return 502, 0, str(exc)
    finally:
        sock.close()


def minecraft(action: str) -> tuple[int, dict]:
    path = {
        "start": f"/v1.43/containers/{MINECRAFT}/start",
        "stop": f"/v1.43/containers/{MINECRAFT}/stop?t=15",
        "restart": f"/v1.43/containers/{MINECRAFT}/restart?t=15",
    }[action]
    status, body = docker("POST", path)
    if status == 404:
        return 409, {"ok": False, "error": "Minecraft is not running. Enable the games profile first."}
    if status >= 300:
        return 502, {"ok": False, "error": body.decode(errors="replace")[:300]}
    return 200, {"ok": True, "action": action}


class Handler(BaseHTTPRequestHandler):
    def _authorized(self) -> bool:
        got = self.headers.get("X-Executor-Token", "")
        return bool(TOKEN) and hmac.compare_digest(got, TOKEN)

    def _send(self, status: int, payload: dict) -> None:
        raw = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _denied(self) -> None:
        self._send(401, {"ok": False, "error": "unauthorized"})

    def do_GET(self) -> None:
        if not self._authorized():
            self._denied()
            return
        if self.path == "/containers":
            self._send(200, {"containers": containers()})
            return
        if self.path == "/minecraft/status":
            status, payload = minecraft_status()
            self._send(status, payload)
            return
        if self.path == "/minecraft/logs":
            status, body = docker("GET", f"/v1.43/containers/{MINECRAFT}/logs?stdout=1&stderr=1&tail=100")
            if status == 404:
                self._send(200, {"logs": "", "error": "Minecraft is not running."})
                return
            self._send(200, {"logs": decode_logs(body)})
            return
        self._send(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:
        if not self._authorized():
            self._denied()
            return
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode() or "{}")
        except json.JSONDecodeError:
            self._send(400, {"ok": False, "error": "bad json"})
            return
        action = body.get("action")
        if action == "llm-stop":
            self._send(200, stop_models())
            return
        if action == "minecraft-start":
            status, payload = minecraft("start")
            self._send(status, payload)
            return
        if action == "minecraft-stop":
            status, payload = minecraft("stop")
            self._send(status, payload)
            return
        if action == "minecraft-restart":
            status, payload = minecraft("restart")
            self._send(status, payload)
            return
        if action == "minecraft-backup":
            status, payload = minecraft_backup()
            self._send(status, payload)
            return
        self._send(404, {"ok": False, "error": "action is not allowlisted"})

    def log_message(self, fmt: str, *args) -> None:
        print("executor", self.address_string(), fmt % args)


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("EXECUTOR_TOKEN is required")
    ThreadingHTTPServer(("0.0.0.0", 8090), Handler).serve_forever()
