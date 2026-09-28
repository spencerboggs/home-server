import json
import urllib.error
import urllib.parse
import urllib.request

from .config import AUTHENTIK_INTERNAL, AUTHENTIK_TOKEN


class AuthentikError(Exception):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


def _request(method: str, path: str, body: dict | None = None) -> dict:
    if not AUTHENTIK_TOKEN:
        raise AuthentikError("Authentik API token is not configured", 503)
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        f"{AUTHENTIK_INTERNAL}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {AUTHENTIK_TOKEN}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:500]
        raise AuthentikError(f"Authentik returned {exc.code}: {detail}", exc.code) from exc
    except (OSError, urllib.error.URLError, json.JSONDecodeError, TimeoutError) as exc:
        raise AuthentikError(f"Authentik is unreachable: {exc}") from exc


def create_invitation(code: str, sponsor: str, role: str, expires: str) -> dict:
    # attributes.* is copied onto the new user by Authentik's user-write stage.
    # The signup URL must use the invitation pk. Authentik looks the token up by that id.
    return _request(
        "POST",
        "/api/v3/stages/invitation/invitations/",
        {
            "name": code,
            "single_use": True,
            "expires": expires,
            "fixed_data": {
                "attributes.referral_code": code,
                "attributes.sponsored_by": sponsor,
                "attributes.intended_role": role,
            },
        },
    )


def delete_invitation(pk: int) -> None:
    _request("DELETE", f"/api/v3/stages/invitation/invitations/{pk}/")


def create_admin(username: str, name: str, email: str, password: str) -> dict:
    groups = _request("GET", "/api/v3/core/groups/?name=administrators&page_size=20")
    results = groups.get("results", [])
    admin_group = next((item for item in results if item.get("name") == "administrators"), None)
    if admin_group is None:
        raise AuthentikError("The administrators group does not exist yet", 503)
    user = _request(
        "POST",
        "/api/v3/core/users/",
        {
            "username": username,
            "name": name,
            "email": email,
            "is_active": True,
            "path": "users",
            "groups": [admin_group["pk"]],
        },
    )
    _request(
        "POST",
        f"/api/v3/core/users/{user['pk']}/set_password/",
        {"password": password},
    )
    return user


def list_users() -> list[dict]:
    users = []
    path = "/api/v3/core/users/?page_size=100"
    while path:
        page = _request("GET", path)
        users.extend(page.get("results", []))
        nxt = (page.get("pagination") or {}).get("next") or ""
        if not nxt:
            break
        marker = "/api/v3/"
        if marker in nxt:
            path = marker + nxt.split(marker, 1)[1]
        elif nxt.startswith("/"):
            path = nxt
        else:
            break
    return users


def ensure_group(user_pk: int | str, group_name: str) -> None:
    groups = _request("GET", f"/api/v3/core/groups/?name={urllib.parse.quote(group_name)}&page_size=20")
    group = next((item for item in groups.get("results", []) if item.get("name") == group_name), None)
    if group is None:
        raise AuthentikError(f"The {group_name} group does not exist yet", 503)
    try:
        _request("POST", f"/api/v3/core/groups/{group['pk']}/add_user/", {"pk": user_pk})
    except AuthentikError as exc:
        if exc.status not in {400, 409}:
            raise
