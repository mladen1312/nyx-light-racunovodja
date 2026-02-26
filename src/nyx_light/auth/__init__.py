"""
Nyx Light — Autentifikacija i Autorizacija

Lokalni auth sustav (ZERO CLOUD):
  - bcrypt hash lozinki
  - JWT tokeni (HS256, lokalni secret)
  - 3 role: admin, racunovodja, asistent
  - Rate limiting za login pokušaje
  - Audit log svakog pristupa
"""

import hashlib
import hmac
import json
import logging
import os
import secrets
import sqlite3
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("nyx_light.auth")


class Role(str, Enum):
    ADMIN = "admin"               # Sve + user management + config
    RACUNOVODJA = "racunovodja"   # Approve/reject + chat + export
    ASISTENT = "asistent"         # Chat + view only (ne može approve)


# Dozvole po roli
ROLE_PERMISSIONS = {
    Role.ADMIN: {
        "chat", "approve", "reject", "correct", "export",
        "view_dashboard", "manage_users", "configure_erp",
        "view_audit", "manage_clients", "auto_book_toggle",
        "backup", "update_model",
    },
    Role.RACUNOVODJA: {
        "chat", "approve", "reject", "correct", "export",
        "view_dashboard", "view_audit", "manage_clients",
    },
    Role.ASISTENT: {
        "chat", "view_dashboard",
    },
}


@dataclass
class User:
    id: str
    username: str
    display_name: str
    role: Role
    password_hash: str = ""
    created_at: str = ""
    last_login: str = ""
    is_active: bool = True
    failed_attempts: int = 0
    locked_until: str = ""


@dataclass
class AuthToken:
    user_id: str
    username: str
    role: Role
    issued_at: float
    expires_at: float


# ═══════════════════════════════════════════════════
# PASSWORD HASHING (PBKDF2 — no external deps)
# ═══════════════════════════════════════════════════

def hash_password(password: str, salt: Optional[bytes] = None) -> str:
    """Hash password s PBKDF2-SHA256 (100k iteracija)."""
    if salt is None:
        salt = os.urandom(32)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return urlsafe_b64encode(salt + dk).decode()


def verify_password(password: str, stored_hash: str) -> bool:
    """Verificiraj password protiv stored hash-a."""
    try:
        decoded = urlsafe_b64decode(stored_hash.encode())
        salt = decoded[:32]
        stored_dk = decoded[32:]
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
        return hmac.compare_digest(dk, stored_dk)
    except Exception:
        return False


# ═══════════════════════════════════════════════════
# JWT (Minimal, no external deps — HS256)
# ═══════════════════════════════════════════════════

def _b64url_encode(data: bytes) -> str:
    return urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    s += "=" * (4 - len(s) % 4)
    return urlsafe_b64decode(s.encode())


def create_jwt(payload: Dict[str, Any], secret: str,
               expires_hours: int = 12) -> str:
    """Kreiraj JWT token (HS256)."""
    header = {"alg": "HS256", "typ": "JWT"}
    payload["iat"] = time.time()
    payload["exp"] = time.time() + expires_hours * 3600

    h = _b64url_encode(json.dumps(header).encode())
    p = _b64url_encode(json.dumps(payload).encode())
    signing_input = f"{h}.{p}"

    sig = hmac.new(
        secret.encode(), signing_input.encode(), hashlib.sha256
    ).digest()
    s = _b64url_encode(sig)

    return f"{h}.{p}.{s}"


def decode_jwt(token: str, secret: str) -> Optional[Dict[str, Any]]:
    """Dekodiraj i verificiraj JWT token."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None

        signing_input = f"{parts[0]}.{parts[1]}"
        expected_sig = hmac.new(
            secret.encode(), signing_input.encode(), hashlib.sha256
        ).digest()
        actual_sig = _b64url_decode(parts[2])

        if not hmac.compare_digest(expected_sig, actual_sig):
            logger.warning("JWT signature mismatch")
            return None

        payload = json.loads(_b64url_decode(parts[1]))

        if payload.get("exp", 0) < time.time():
            logger.info("JWT expired")
            return None

        return payload
    except Exception as e:
        logger.error("JWT decode error: %s", e)
        return None


# ═══════════════════════════════════════════════════
# AUTH MANAGER
# ═══════════════════════════════════════════════════

class AuthManager:
    """Centralni auth manager — SQLite backend."""

    MAX_FAILED_ATTEMPTS = 5
    LOCKOUT_MINUTES = 15

    def __init__(self, db_path: str = "data/auth.db"):
        self.db_path = db_path
        self._secret = ""
        self._init_db()

    def _init_db(self):
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                display_name TEXT NOT NULL,
                role TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_login TEXT,
                is_active INTEGER DEFAULT 1,
                failed_attempts INTEGER DEFAULT 0,
                locked_until TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                user_id TEXT,
                username TEXT,
                action TEXT NOT NULL,
                details TEXT,
                ip_address TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        conn.commit()

        # JWT secret — generiraj jednom, spremi u DB
        row = conn.execute(
            "SELECT value FROM config WHERE key='jwt_secret'"
        ).fetchone()
        if row:
            self._secret = row[0]
        else:
            self._secret = secrets.token_hex(32)
            conn.execute(
                "INSERT INTO config (key, value) VALUES (?, ?)",
                ("jwt_secret", self._secret),
            )
            conn.commit()

        # Default admin ako nema korisnika
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if count == 0:
            self.create_user("admin", "admin", "Administrator",
                             Role.ADMIN, _conn=conn)
            logger.info("Default admin kreiran (username: admin, password: admin)")

        conn.close()

    # ════════════════════════════════════════
    # USER CRUD
    # ════════════════════════════════════════

    def create_user(self, username: str, password: str,
                    display_name: str, role: Role,
                    _conn=None) -> Optional[User]:
        """Kreiraj novog korisnika."""
        close = _conn is None
        conn = _conn or sqlite3.connect(self.db_path)
        try:
            user_id = f"u_{secrets.token_hex(8)}"
            pw_hash = hash_password(password)
            now = datetime.now().isoformat()
            conn.execute(
                """INSERT INTO users
                   (id, username, display_name, role, password_hash, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (user_id, username, display_name, role.value, pw_hash, now),
            )
            conn.commit()
            logger.info("User created: %s (%s)", username, role.value)
            return User(
                id=user_id, username=username,
                display_name=display_name, role=role,
                password_hash=pw_hash, created_at=now,
            )
        except sqlite3.IntegrityError:
            logger.error("Username already exists: %s", username)
            return None
        finally:
            if close:
                conn.close()

    def get_user(self, username: str) -> Optional[User]:
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT * FROM users WHERE username=?", (username,)
        ).fetchone()
        conn.close()
        if not row:
            return None
        return User(
            id=row[0], username=row[1], display_name=row[2],
            role=Role(row[3]), password_hash=row[4],
            created_at=row[5], last_login=row[6] or "",
            is_active=bool(row[7]), failed_attempts=row[8],
            locked_until=row[9] or "",
        )

    def list_users(self) -> List[User]:
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute("SELECT * FROM users ORDER BY username").fetchall()
        conn.close()
        return [
            User(id=r[0], username=r[1], display_name=r[2],
                 role=Role(r[3]), password_hash="[hidden]",
                 created_at=r[5], last_login=r[6] or "",
                 is_active=bool(r[7]))
            for r in rows
        ]

    def update_user(self, username: str, **kwargs) -> bool:
        conn = sqlite3.connect(self.db_path)
        allowed = {"display_name", "role", "is_active"}
        sets = []
        vals = []
        for k, v in kwargs.items():
            if k in allowed:
                sets.append(f"{k}=?")
                vals.append(v.value if isinstance(v, Role) else v)
        if not sets:
            conn.close()
            return False
        vals.append(username)
        conn.execute(f"UPDATE users SET {','.join(sets)} WHERE username=?", vals)
        conn.commit()
        conn.close()
        return True

    def change_password(self, username: str, new_password: str) -> bool:
        conn = sqlite3.connect(self.db_path)
        pw_hash = hash_password(new_password)
        conn.execute(
            "UPDATE users SET password_hash=? WHERE username=?",
            (pw_hash, username),
        )
        conn.commit()
        conn.close()
        return True

    def delete_user(self, username: str) -> bool:
        conn = sqlite3.connect(self.db_path)
        conn.execute("DELETE FROM users WHERE username=?", (username,))
        conn.commit()
        conn.close()
        return True

    # ════════════════════════════════════════
    # LOGIN / LOGOUT
    # ════════════════════════════════════════

    def login(self, username: str, password: str,
              ip: str = "") -> Dict[str, Any]:
        """Login → JWT token ili error."""
        user = self.get_user(username)
        if not user:
            self._audit("login_failed", None, username,
                        f"Unknown user: {username}", ip)
            return {"ok": False, "error": "Nepoznati korisnik"}

        # Account lock check
        if user.locked_until:
            lock_time = datetime.fromisoformat(user.locked_until)
            if datetime.now() < lock_time:
                remaining = int((lock_time - datetime.now()).total_seconds() / 60)
                return {"ok": False,
                        "error": f"Račun zaključan. Pokušajte za {remaining} min."}
            # Lock expired → reset
            self._reset_failed(username)

        if not user.is_active:
            return {"ok": False, "error": "Račun deaktiviran"}

        if not verify_password(password, user.password_hash):
            self._record_failed(username)
            self._audit("login_failed", user.id, username,
                        "Wrong password", ip)
            remaining = self.MAX_FAILED_ATTEMPTS - user.failed_attempts - 1
            if remaining <= 0:
                return {"ok": False,
                        "error": f"Račun zaključan na {self.LOCKOUT_MINUTES} min."}
            return {"ok": False,
                    "error": f"Pogrešna lozinka ({remaining} pokušaja preostalo)"}

        # Success
        self._reset_failed(username)
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "UPDATE users SET last_login=? WHERE username=?",
            (datetime.now().isoformat(), username),
        )
        conn.commit()
        conn.close()

        token = create_jwt({
            "sub": user.id,
            "username": username,
            "role": user.role.value,
            "name": user.display_name,
        }, self._secret)

        self._audit("login_success", user.id, username, "", ip)

        return {
            "ok": True,
            "token": token,
            "user": {
                "id": user.id,
                "username": username,
                "display_name": user.display_name,
                "role": user.role.value,
                "permissions": sorted(ROLE_PERMISSIONS[user.role]),
            },
        }

    def verify_token(self, token: str) -> Optional[AuthToken]:
        """Verificiraj JWT → AuthToken ili None."""
        payload = decode_jwt(token, self._secret)
        if not payload:
            return None
        return AuthToken(
            user_id=payload.get("sub", ""),
            username=payload.get("username", ""),
            role=Role(payload.get("role", "asistent")),
            issued_at=payload.get("iat", 0),
            expires_at=payload.get("exp", 0),
        )

    def has_permission(self, token: str, permission: str) -> bool:
        """Provjeri ima li token-holder dozvolu."""
        auth = self.verify_token(token)
        if not auth:
            return False
        return permission in ROLE_PERMISSIONS.get(auth.role, set())

    # ════════════════════════════════════════
    # AUDIT LOG
    # ════════════════════════════════════════

    def _audit(self, action: str, user_id: Optional[str],
               username: str, details: str, ip: str = ""):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """INSERT INTO audit_log
               (timestamp, user_id, username, action, details, ip_address)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (datetime.now().isoformat(), user_id, username,
             action, details, ip),
        )
        conn.commit()
        conn.close()

    def get_audit_log(self, limit: int = 100) -> List[Dict]:
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        return [
            {"id": r[0], "timestamp": r[1], "user_id": r[2],
             "username": r[3], "action": r[4],
             "details": r[5], "ip": r[6]}
            for r in rows
        ]

    def log_action(self, user_id: str, username: str,
                   action: str, details: str = "", ip: str = ""):
        """Javni audit log za druge module."""
        self._audit(action, user_id, username, details, ip)

    # ════════════════════════════════════════
    # INTERNAL HELPERS
    # ════════════════════════════════════════

    def _record_failed(self, username: str):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "UPDATE users SET failed_attempts = failed_attempts + 1 WHERE username=?",
            (username,),
        )
        row = conn.execute(
            "SELECT failed_attempts FROM users WHERE username=?", (username,)
        ).fetchone()
        if row and row[0] >= self.MAX_FAILED_ATTEMPTS:
            lock = (datetime.now() +
                    timedelta(minutes=self.LOCKOUT_MINUTES)).isoformat()
            conn.execute(
                "UPDATE users SET locked_until=? WHERE username=?",
                (lock, username),
            )
        conn.commit()
        conn.close()

    def _reset_failed(self, username: str):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "UPDATE users SET failed_attempts=0, locked_until=NULL WHERE username=?",
            (username,),
        )
        conn.commit()
        conn.close()
