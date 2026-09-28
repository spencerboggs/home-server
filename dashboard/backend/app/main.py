import hashlib
import json
import secrets
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import authentik_api, stats, store
from .authentik_api import AuthentikError
from .config import (
    AUTHENTIK_BROWSER,
    AUTHENTIK_INTERNAL,
    CHAT_RETENTION_DAYS,
    COOLIFY_API_TOKEN,
    COOLIFY_API_URL,
    DEV_AUTH,
    EXECUTOR_TOKEN,
    EXECUTOR_URL,
    HOSTS,
    LLMLINGUA_URL,
    OIDC_CLIENT_ID,
    OIDC_SECRET,
    PUBLIC_URL,
    REDIS_URL,
    SESSION_HOURS,
    VLLM_MANAGER_MODEL,
    VLLM_MANAGER_URL,
    VLLM_MODEL,
    VLLM_URL,
    WEBSITES_FILE,
)

app = FastAPI(title="The Server")
STATIC = Path(__file__).resolve().parent.parent / "static"
COOKIE = "server_session"


@app.on_event("startup")
def startup() -> None:
    store.init()
    threading.Thread(target=_referral_loop, name="referral-sync", daemon=True).start()


def _referral_loop() -> None:
    import time

    time.sleep(5)
    while True:
        _sync_referrals()
        time.sleep(120)


def _sync_referrals() -> None:
    try:
        users = authentik_api.list_users()
    except AuthentikError:
        return
    for person in users:
        attrs = person.get("attributes") or {}
        code = str(attrs.get("referral_code") or "").strip()
        username = str(person.get("username") or "").strip()
        if not code or not username:
            continue
        used_at = str(person.get("date_joined") or store.iso(store.now()))
        if store.mark_referral_used(code, username, used_at):
            store.audit(username, "account_created", json.dumps({"username": username, "code": code}))
        role = str(attrs.get("intended_role") or "user")
        group = "administrators" if role == "administrator" else "users"
        try:
            authentik_api.ensure_group(person["pk"], group)
        except AuthentikError:
            continue


def _user(request: Request) -> dict | None:
    return store.read_session(request.cookies.get(COOKIE, ""))


def _require(request: Request) -> dict:
    user = _user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Sign in required")
    return user


def _admin(request: Request) -> dict:
    user = _require(request)
    if not _is_admin(user):
        raise HTTPException(status_code=403, detail="Administrator required")
    return user


def _is_admin(user: dict) -> bool:
    return user["username"] == "akadmin" or "administrators" in user["groups"]


def _public_user(user: dict) -> dict:
    return {
        "username": user["username"],
        "display_name": user["display_name"],
        "email": user["email"],
        "admin": _is_admin(user),
    }


@app.get("/health")
def health() -> JSONResponse:
    response = JSONResponse({"status": "online"})
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/me")
def me(request: Request) -> dict:
    user = _user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Sign in required")
    return _public_user(user)


@app.get("/api/auth/login")
def login() -> RedirectResponse:
    state = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = _b64(digest)
    store.put_state(state, verifier)
    query = urllib.parse.urlencode(
        {
            "client_id": OIDC_CLIENT_ID,
            "response_type": "code",
            "scope": "openid email profile groups",
            "redirect_uri": f"{PUBLIC_URL}/api/auth/callback",
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    return RedirectResponse(f"{AUTHENTIK_BROWSER}/application/o/authorize/?{query}")


def _b64(raw: bytes) -> str:
    import base64

    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


@app.get("/api/auth/callback")
def callback(code: str = "", state: str = "", error: str = "") -> RedirectResponse:
    if error or not code or not state:
        return RedirectResponse("/?auth=failed")
    verifier = store.pop_state(state)
    if not verifier:
        return RedirectResponse("/?auth=failed")
    try:
        token = _form(
            f"{AUTHENTIK_INTERNAL}/application/o/token/",
            {
                "grant_type": "authorization_code",
                "client_id": OIDC_CLIENT_ID,
                "client_secret": OIDC_SECRET,
                "code": code,
                "redirect_uri": f"{PUBLIC_URL}/api/auth/callback",
                "code_verifier": verifier,
            },
        )
        access = token.get("access_token")
        if not access:
            return RedirectResponse("/?auth=failed")
        _sync_referrals()
        info = _get_json(
            f"{AUTHENTIK_INTERNAL}/application/o/userinfo/",
            {"Authorization": f"Bearer {access}"},
        )
    except Exception:
        return RedirectResponse("/?auth=failed")
    username = info.get("preferred_username") or info.get("nickname") or info.get("sub")
    if not username:
        return RedirectResponse("/?auth=failed")
    groups = info.get("groups") or []
    if isinstance(groups, str):
        groups = [groups]
    session_id = store.create_session(
        username=username,
        display_name=info.get("name") or username,
        email=info.get("email") or "",
        groups=list(groups),
        hours=SESSION_HOURS,
    )
    store.audit(username, "login", "dashboard")
    response = RedirectResponse("/")
    response.set_cookie(
        COOKIE,
        session_id,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=SESSION_HOURS * 3600,
        path="/",
    )
    return response


@app.post("/api/auth/logout")
def logout(request: Request) -> JSONResponse:
    session_id = request.cookies.get(COOKIE, "")
    user = store.read_session(session_id)
    if session_id:
        store.delete_session(session_id)
    if user:
        store.audit(user["username"], "logout", "dashboard")
    response = JSONResponse({"ok": True})
    response.delete_cookie(COOKIE, path="/")
    return response


@app.get("/api/auth/dev")
def dev_login() -> JSONResponse:
    if not DEV_AUTH:
        raise HTTPException(status_code=404, detail="Not found")
    session_id = store.create_session("akadmin", "Dev Admin", "dev@localhost", ["administrators"], 12)
    response = JSONResponse({"ok": True})
    response.set_cookie(COOKIE, session_id, httponly=True, samesite="lax", path="/")
    return response


@app.get("/api/server/stats")
def server_stats(request: Request) -> dict:
    _require(request)
    return stats.stats()


@app.get("/api/processes")
def processes(request: Request) -> dict:
    user = _require(request)
    return {"admin": _is_admin(user), "processes": stats.processes()}


@app.get("/api/services")
def services(request: Request) -> dict:
    _require(request)
    listed = _executor("GET", "/containers") or {}
    containers = listed.get("containers", []) if isinstance(listed, dict) else []
    by_name = {str(item.get("name", "")).lstrip("/"): item for item in containers}
    catalog = _catalog()
    for item in catalog:
        live = by_name.get(item["container"], {})
        item["state"] = live.get("state") or "absent"
        item["status"] = live.get("status") or "not started"
    return {"services": catalog}


@app.get("/api/websites")
def websites(request: Request) -> dict:
    _require(request)
    rows = _static_websites()
    seen = {item.get("url") for item in rows}
    for item in _coolify_websites():
        if item.get("url") not in seen:
            rows.append(item)
            seen.add(item.get("url"))
    return {"websites": rows}


def _static_websites() -> list[dict]:
    path = Path(WEBSITES_FILE)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _coolify_websites() -> list[dict]:
    if not COOLIFY_API_TOKEN:
        return []
    request = urllib.request.Request(
        f"{COOLIFY_API_URL}/api/v1/applications",
        headers={"Authorization": f"Bearer {COOLIFY_API_TOKEN}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            payload = json.loads(response.read().decode())
    except (OSError, urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        return []
    apps = payload if isinstance(payload, list) else payload.get("applications", [])
    rows = []
    for app_row in apps:
        if not isinstance(app_row, dict):
            continue
        url = str(app_row.get("fqdn") or app_row.get("url") or "")
        name = str(app_row.get("name") or "Application")
        repo = str(app_row.get("git_repository") or app_row.get("git_full_url") or "")
        status = str(app_row.get("status") or "")
        detail = " ".join(part for part in (repo, status) if part)
        rows.append({"name": name, "url": url, "description": detail or "Coolify application"})
    return rows


@app.get("/api/links")
def links(request: Request) -> dict:
    _require(request)
    return {
        "media": _https("media"),
        "git": _https("git"),
        "files": _https("files"),
        "office": _https("office"),
        "apps": _https("apps"),
        "notify": _https("notify"),
        "grafana": _https("grafana"),
        "auth": _https("auth"),
    }


@app.get("/api/chat")
def chat_history(request: Request) -> dict:
    _require(request)
    return {"messages": store.list_chat(), "retention_days": CHAT_RETENTION_DAYS}


@app.post("/api/chat")
async def chat_post(request: Request) -> dict:
    user = _require(request)
    body = await request.json()
    text = str(body.get("body") or "").strip()
    if not text or len(text) > 2000:
        raise HTTPException(status_code=400, detail="Message must be 1 to 2000 characters")
    message = store.add_chat(user["username"], text)
    await hub.broadcast({"type": "chat", "message": message})
    _publish(message)
    return message


@app.get("/api/audit")
def audit_log(request: Request) -> dict:
    _admin(request)
    return {"events": store.list_audit()}


@app.get("/api/referrals")
def referrals(request: Request) -> dict:
    _admin(request)
    _sync_referrals()
    return {"referrals": store.list_referrals()}


@app.post("/api/referrals")
async def create_referral(request: Request) -> dict:
    user = _admin(request)
    body = await request.json()
    role = body.get("role") or "user"
    if role not in {"user", "administrator"}:
        raise HTTPException(status_code=400, detail="Role must be user or administrator")
    note = str(body.get("note") or "")[:200]
    code = secrets.token_hex(4).upper()
    expires = (store.now() + timedelta(days=14)).isoformat()
    try:
        created = authentik_api.create_invitation(code, user["username"], role, expires)
    except AuthentikError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    store.add_referral(code, user["username"], role, note, created.get("pk"))
    store.audit(user["username"], "referral_issued", json.dumps({"code": code, "role": role}))
    token = str(created.get("pk") or "")
    if not token:
        raise HTTPException(status_code=502, detail="Authentik did not return an invitation id")
    signup_url = f"{AUTHENTIK_BROWSER}/if/flow/default-enrollment-flow/?itoken={token}"
    return {"code": code, "signup_url": signup_url, "sponsor": user["username"], "role": role, "expires": expires}


@app.post("/api/referrals/{code}/revoke")
def revoke_referral(code: str, request: Request) -> dict:
    user = _admin(request)
    row = store.revoke_referral(code)
    if row is None:
        raise HTTPException(status_code=404, detail="Unknown code")
    if row.get("authentik_pk"):
        try:
            authentik_api.delete_invitation(int(row["authentik_pk"]))
        except AuthentikError:
            pass
    store.audit(user["username"], "referral_revoked", code)
    return {"ok": True}


@app.post("/api/admins")
async def create_admin(request: Request) -> dict:
    user = _admin(request)
    body = await request.json()
    username = str(body.get("username") or "").strip()
    name = str(body.get("name") or username).strip()
    email = str(body.get("email") or "").strip()
    password = str(body.get("password") or "")
    if not username or not email or len(password) < 12:
        raise HTTPException(status_code=400, detail="Username, email, and a 12+ character password are required")
    try:
        created = authentik_api.create_admin(username, name, email, password)
    except AuthentikError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    store.audit(
        user["username"],
        "account_created",
        json.dumps({"username": username, "sponsor": user["username"], "code": "direct", "role": "administrator"}),
    )
    return {"username": created.get("username", username), "sponsor": user["username"]}


@app.post("/api/admin/actions/{name}")
async def admin_action(name: str, request: Request) -> dict:
    user = _admin(request)
    allowed = {"llm-stop", "minecraft-start", "minecraft-stop", "minecraft-restart", "minecraft-backup"}
    if name not in allowed:
        raise HTTPException(status_code=404, detail="Unknown action")
    result = _executor("POST", "/actions", {"action": name})
    if result is None:
        raise HTTPException(status_code=502, detail="Executor refused the action")
    store.audit(user["username"], "admin_action", name)
    return result


@app.get("/api/minecraft/status")
def minecraft_status(request: Request) -> dict:
    _require(request)
    result = _executor("GET", "/minecraft/status")
    if result is None:
        return {"online": False, "players": "", "version": "", "detail": "Executor is unavailable"}
    return result
def minecraft_logs(request: Request) -> dict:
    _admin(request)
    result = _executor("GET", "/minecraft/logs")
    if result is None:
        raise HTTPException(status_code=502, detail="Executor is unavailable")
    return result


@app.get("/api/llm/status")
def llm_status(request: Request) -> dict:
    _require(request)
    return {
        "model": VLLM_MODEL or None,
        "configured": bool(VLLM_MODEL),
        "manager_model": VLLM_MANAGER_MODEL or None,
        "manager_configured": bool(VLLM_MANAGER_MODEL),
    }


@app.post("/api/llm/chat")
async def llm_chat(request: Request) -> dict:
    user = _require(request)
    if not VLLM_MODEL:
        raise HTTPException(status_code=503, detail="No model is configured. An administrator sets VLLM_MODEL and starts the ai profile.")
    body = await request.json()
    messages = body.get("messages")
    if not isinstance(messages, list) or not messages:
        raise HTTPException(status_code=400, detail="messages is required")
    cleaned = []
    for item in messages[-20:]:
        role = item.get("role")
        content = str(item.get("content") or "")
        if role not in {"user", "assistant"} or not content or len(content) > 8000:
            continue
        cleaned.append({"role": role, "content": content})
    if not cleaned:
        raise HTTPException(status_code=400, detail="No usable messages")
    compressed = False
    blob = "\n".join(item["content"] for item in cleaned)
    if len(blob) > 1500:
        shortened = _compress(blob)
        if shortened is None:
            raise HTTPException(status_code=503, detail="LLMLingua is not available for this long prompt")
        cleaned = [{"role": "user", "content": shortened}]
        compressed = True
    snapshot = stats.stats()
    payload = {
        "model": VLLM_MODEL,
        "temperature": 0.4,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are the server chat assistant. You cannot run commands, change files, or approve actions. "
                    "If asked about resources, use only this JSON and do not invent numbers: "
                    + json.dumps(snapshot)
                ),
            },
            *cleaned,
        ],
    }
    try:
        result = _post_json(f"{VLLM_URL}/v1/chat/completions", payload)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"vLLM is not available: {exc}") from exc
    try:
        text = result["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise HTTPException(status_code=502, detail="vLLM returned an unexpected response") from exc
    store.audit(user["username"], "llm_request", VLLM_MODEL)
    return {"content": text, "compressed": compressed, "model": VLLM_MODEL}


@app.post("/api/llm/manager")
async def llm_manager(request: Request) -> dict:
    user = _admin(request)
    if not VLLM_MANAGER_MODEL:
        raise HTTPException(status_code=503, detail="No manager model is configured. Set VLLM_MANAGER_MODEL and start it with the ai profile.")
    body = await request.json()
    messages = body.get("messages")
    if not isinstance(messages, list) or not messages:
        raise HTTPException(status_code=400, detail="messages is required")
    cleaned = []
    for item in messages[-12:]:
        role = item.get("role")
        content = str(item.get("content") or "")
        if role not in {"user", "assistant"} or not content or len(content) > 4000:
            continue
        cleaned.append({"role": role, "content": content})
    if not cleaned:
        raise HTTPException(status_code=400, detail="No usable messages")
    snapshot = stats.stats()
    payload = {
        "model": VLLM_MANAGER_MODEL,
        "temperature": 0.2,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are the server manager assistant. You may summarize these stats and recommend a next step. "
                    "You cannot run commands, change files, start containers, or approve actions. "
                    "Use only this JSON for numbers: "
                    + json.dumps(snapshot)
                ),
            },
            *cleaned,
        ],
    }
    try:
        result = _post_json(f"{VLLM_MANAGER_URL}/v1/chat/completions", payload)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"The manager model is not available: {exc}") from exc
    try:
        text = result["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise HTTPException(status_code=502, detail="The manager model returned an unexpected response") from exc
    store.audit(user["username"], "llm_manager_request", VLLM_MANAGER_MODEL)
    return {"content": text, "model": VLLM_MANAGER_MODEL}


class Hub:
    def __init__(self) -> None:
        self.sockets: set[WebSocket] = set()

    async def connect(self, socket: WebSocket) -> None:
        await socket.accept()
        self.sockets.add(socket)

    def drop(self, socket: WebSocket) -> None:
        self.sockets.discard(socket)

    async def broadcast(self, message: dict) -> None:
        dead = []
        for socket in self.sockets:
            try:
                await socket.send_json(message)
            except Exception:
                dead.append(socket)
        for socket in dead:
            self.drop(socket)


hub = Hub()


@app.websocket("/api/ws")
async def websocket(socket: WebSocket) -> None:
    session_id = socket.cookies.get(COOKIE, "")
    user = store.read_session(session_id)
    if user is None:
        await socket.close(code=4401)
        return
    await hub.connect(socket)
    try:
        while True:
            raw = await socket.receive_text()
            try:
                incoming = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if incoming.get("type") == "chat":
                text = str(incoming.get("body") or "").strip()
                if not text or len(text) > 2000:
                    continue
                message = store.add_chat(user["username"], text)
                await hub.broadcast({"type": "chat", "message": message})
            elif incoming.get("type") == "stats":
                await socket.send_json({"type": "stats", "stats": stats.stats()})
    except WebSocketDisconnect:
        hub.drop(socket)


def _publish(message: dict) -> None:
    if not REDIS_URL:
        return
    try:
        import redis

        client = redis.Redis.from_url(REDIS_URL, socket_timeout=1)
        client.publish("chat", json.dumps(message))
    except Exception:
        return


def _catalog() -> list[dict]:
    return [
        _service("Dashboard", "server-dashboard", "dashboard", "The front door for people using the server."),
        _service("Authentik", "server-authentik", "auth", "Accounts, roles, and referral signup."),
        _service("Grafana", "server-grafana", "grafana", "Metrics and log search for administrators."),
        _service("ntfy", "server-ntfy", "notify", "Admin alerts and general announcements."),
        _service("Jellyfin", "server-jellyfin", "media", "Movies, TV, music, and photos."),
        _service("Forgejo", "server-forgejo", "git", "Private git repositories."),
        _service("Nextcloud", "server-nextcloud", "files", "Files, documents, and spreadsheets."),
        _service("Collabora", "server-collabora", "office", "Browser editing for Nextcloud documents."),
        _service("Coolify", "server-coolify", "apps", "Git-based application deploys."),
        _service("Minecraft", "server-minecraft", "", "Game server on port 25565 when the games profile is on."),
        _service("vLLM", "server-vllm", "", "Local chat model. Not published to the internet."),
        _service("vLLM manager", "server-vllm-manager", "", "Always-on manager model. Recommendations only."),
        _service("LLMLingua", "server-llmlingua", "", "Compresses long prompts before they reach vLLM."),
        _service("Lavalink", "server-lavalink", "", "Audio backend for the Discord bot."),
        _service("Discord bot", "server-discord-bot", "", "Status and music. The token stays on the server."),
    ]


def _service(name: str, container: str, host_key: str, description: str) -> dict:
    return {
        "name": name,
        "container": container,
        "url": _https(host_key) if host_key else "",
        "description": description,
        "state": "unknown",
        "status": "",
    }


def _https(key: str) -> str:
    host = HOSTS.get(key) or ""
    if not host or host.endswith("example.com"):
        return ""
    return f"https://{host}"


def _executor(method: str, path: str, body: dict | None = None) -> dict | None:
    if not EXECUTOR_TOKEN:
        return None
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        f"{EXECUTOR_URL}{path}",
        data=data,
        method=method,
        headers={
            "X-Executor-Token": EXECUTOR_TOKEN,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode()
            parsed = json.loads(raw) if raw else {}
            return parsed if isinstance(parsed, dict) else {"items": parsed}
    except urllib.error.HTTPError:
        return None
    except (OSError, urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        return None


def _form(url: str, fields: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(fields).encode(),
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json", "Host": _auth_host()},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode())


def _get_json(url: str, headers: dict) -> dict:
    request = urllib.request.Request(url, headers={**headers, "Accept": "application/json", "Host": _auth_host()})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode())


def _post_json(url: str, body: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode())


def _compress(text: str) -> str | None:
    try:
        result = _post_json(f"{LLMLINGUA_URL}/compress", {"text": text})
    except Exception:
        return None
    shortened = result.get("text")
    return shortened if isinstance(shortened, str) and shortened else None


def _auth_host() -> str:
    return urllib.parse.urlparse(AUTHENTIK_BROWSER).netloc


if STATIC.exists():
    app.mount("/assets", StaticFiles(directory=STATIC / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str) -> FileResponse:
        target = STATIC / full_path
        if full_path and target.is_file():
            return FileResponse(target)
        return FileResponse(STATIC / "index.html")
