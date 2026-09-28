import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import CHAT_RETENTION_DAYS, DATA_DIR

_lock = threading.Lock()


def _path() -> Path:
    root = Path(DATA_DIR)
    root.mkdir(parents=True, exist_ok=True)
    return root / "server.db"


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init() -> None:
    with _lock, connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                display_name TEXT,
                email TEXT,
                groups TEXT,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS oauth_states (
                state TEXT PRIMARY KEY,
                verifier TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS referrals (
                code TEXT PRIMARY KEY,
                sponsor TEXT NOT NULL,
                role TEXT NOT NULL,
                note TEXT,
                created_at TEXT NOT NULL,
                revoked_at TEXT,
                used_by TEXT,
                used_at TEXT,
                authentik_pk INTEGER
            );
            CREATE TABLE IF NOT EXISTS audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                at TEXT NOT NULL,
                actor TEXT,
                event TEXT NOT NULL,
                detail TEXT
            );
            CREATE TABLE IF NOT EXISTS chat (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                at TEXT NOT NULL,
                username TEXT NOT NULL,
                body TEXT NOT NULL
            );
            """
        )


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime) -> str:
    return value.isoformat()


def audit(actor: str | None, event: str, detail: str = "") -> None:
    with _lock, connect() as conn:
        conn.execute(
            "INSERT INTO audit (at, actor, event, detail) VALUES (?, ?, ?, ?)",
            (iso(now()), actor, event, detail),
        )


def put_state(state: str, verifier: str) -> None:
    with _lock, connect() as conn:
        conn.execute(
            "INSERT INTO oauth_states (state, verifier, created_at) VALUES (?, ?, ?)",
            (state, verifier, iso(now())),
        )


def pop_state(state: str) -> str | None:
    with _lock, connect() as conn:
        row = conn.execute("SELECT verifier FROM oauth_states WHERE state = ?", (state,)).fetchone()
        conn.execute("DELETE FROM oauth_states WHERE state = ?", (state,))
        return None if row is None else row["verifier"]


def create_session(username: str, display_name: str, email: str, groups: list[str], hours: int) -> str:
    import secrets

    session_id = secrets.token_urlsafe(32)
    created = now()
    with _lock, connect() as conn:
        conn.execute(
            """
            INSERT INTO sessions (id, username, display_name, email, groups, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                username,
                display_name,
                email,
                ",".join(groups),
                iso(created),
                iso(created + timedelta(hours=hours)),
            ),
        )
    return session_id


def read_session(session_id: str) -> dict | None:
    if not session_id:
        return None
    with _lock, connect() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if row is None:
        return None
    expires = datetime.fromisoformat(row["expires_at"])
    if expires < now():
        delete_session(session_id)
        return None
    return {
        "username": row["username"],
        "display_name": row["display_name"] or row["username"],
        "email": row["email"] or "",
        "groups": [item for item in (row["groups"] or "").split(",") if item],
    }


def delete_session(session_id: str) -> None:
    with _lock, connect() as conn:
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))


def add_referral(code: str, sponsor: str, role: str, note: str, authentik_pk: int | None) -> None:
    with _lock, connect() as conn:
        conn.execute(
            """
            INSERT INTO referrals (code, sponsor, role, note, created_at, authentik_pk)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (code, sponsor, role, note, iso(now()), authentik_pk),
        )


def list_referrals() -> list[dict]:
    with _lock, connect() as conn:
        rows = conn.execute("SELECT * FROM referrals ORDER BY created_at DESC").fetchall()
    return [dict(row) for row in rows]


def mark_referral_used(code: str, username: str, used_at: str) -> bool:
    with _lock, connect() as conn:
        row = conn.execute(
            "SELECT used_by, revoked_at FROM referrals WHERE code = ?",
            (code,),
        ).fetchone()
        if row is None or row["used_by"] or row["revoked_at"]:
            return False
        conn.execute(
            "UPDATE referrals SET used_by = ?, used_at = ? WHERE code = ?",
            (username, used_at, code),
        )
    return True


def revoke_referral(code: str) -> dict | None:
    with _lock, connect() as conn:
        row = conn.execute("SELECT * FROM referrals WHERE code = ?", (code,)).fetchone()
        if row is None:
            return None
        conn.execute("UPDATE referrals SET revoked_at = ? WHERE code = ?", (iso(now()), code))
        fresh = conn.execute("SELECT * FROM referrals WHERE code = ?", (code,)).fetchone()
    return dict(fresh) if fresh else None


def list_audit(limit: int = 200) -> list[dict]:
    with _lock, connect() as conn:
        rows = conn.execute("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(row) for row in rows]


def add_chat(username: str, body: str) -> dict:
    stamp = iso(now())
    with _lock, connect() as conn:
        cur = conn.execute(
            "INSERT INTO chat (at, username, body) VALUES (?, ?, ?)",
            (stamp, username, body),
        )
        message_id = cur.lastrowid
        cutoff = iso(now() - timedelta(days=CHAT_RETENTION_DAYS))
        conn.execute("DELETE FROM chat WHERE at < ?", (cutoff,))
    return {"id": message_id, "at": stamp, "username": username, "body": body}


def list_chat(limit: int = 200) -> list[dict]:
    with _lock, connect() as conn:
        rows = conn.execute(
            "SELECT * FROM chat ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in reversed(rows)]
