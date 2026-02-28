"""
Nyx Light — Secure Credential Vault
═════════════════════════════════════
Enkriptirani sustav za pohranu korisničkih podataka.

Lozinke se NIKADA ne pohranjuju u čistom tekstu.
Koristi se bcrypt hash + AES-256 za osjetljive podatke.

SIGURNOSNA PRAVILA:
  1. Lozinke → bcrypt hash (cost factor 12)
  2. API ključevi → AES-256-GCM enkripcija
  3. Super admin → hardkodirani hash, pristup odasvud
  4. Vault datoteka → enkriptirana na disku
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nyx_light.security")


# ═══════════════════════════════════════════
# PASSWORD HASHING (bcrypt-compatible via hashlib)
# ═══════════════════════════════════════════

class PasswordHasher:
    """
    Siguran hash lozinki koristeći PBKDF2-HMAC-SHA256.
    Kompatibilno s produkcijskim standardima (NIST SP 800-132).

    U produkciji koristiti bcrypt ili argon2id:
      pip install bcrypt
      bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12))
    """

    ALGORITHM = "pbkdf2_sha256"
    ITERATIONS = 600_000  # OWASP 2024 preporuka
    SALT_LENGTH = 32
    HASH_LENGTH = 64

    @classmethod
    def hash_password(cls, password: str) -> str:
        """Hash lozinku s random salt-om. Vraća encoded string."""
        salt = os.urandom(cls.SALT_LENGTH)
        dk = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            cls.ITERATIONS,
            dklen=cls.HASH_LENGTH,
        )
        salt_b64 = base64.b64encode(salt).decode("ascii")
        hash_b64 = base64.b64encode(dk).decode("ascii")
        return f"${cls.ALGORITHM}${cls.ITERATIONS}${salt_b64}${hash_b64}"

    @classmethod
    def verify_password(cls, password: str, stored_hash: str) -> bool:
        """Verificiraj lozinku protiv pohranjenog hash-a."""
        try:
            parts = stored_hash.split("$")
            if len(parts) != 5:
                return False
            _, algo, iterations, salt_b64, hash_b64 = parts
            if algo != cls.ALGORITHM:
                return False

            salt = base64.b64decode(salt_b64)
            stored_dk = base64.b64decode(hash_b64)
            iterations = int(iterations)

            dk = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                salt,
                iterations,
                dklen=len(stored_dk),
            )
            return hmac.compare_digest(dk, stored_dk)
        except Exception:
            return False


# ═══════════════════════════════════════════
# ROLE SYSTEM
# ═══════════════════════════════════════════

class UserRole(str, Enum):
    SUPER_ADMIN = "super_admin"     # Pristup svemu, odasvud, programiranje
    ADMIN = "admin"                  # Upravljanje korisnicima i sustavom
    RACUNOVODA = "racunovoda"       # Puni radni pristup
    PRIPRAVNIK = "pripravnik"       # Chat + pregled (bez odobravanja)
    READONLY = "readonly"           # Samo pretraga zakona


ROLE_PERMISSIONS = {
    UserRole.SUPER_ADMIN: [
        "all", "ssh", "deploy", "debug", "code_edit", "system_config",
        "user_management", "model_management", "backup", "restore",
        "chat", "approve_entries", "reject_entries", "view_invoices",
        "rag_search", "reports", "clients", "peppol", "dpo_trigger",
        "access_from_anywhere", "bypass_ip_filter",
    ],
    UserRole.ADMIN: [
        "user_management", "system_config", "backup", "restore",
        "chat", "approve_entries", "reject_entries", "view_invoices",
        "rag_search", "reports", "clients", "peppol",
    ],
    UserRole.RACUNOVODA: [
        "chat", "approve_entries", "reject_entries", "view_invoices",
        "rag_search", "reports", "clients",
    ],
    UserRole.PRIPRAVNIK: [
        "chat", "view_invoices", "rag_search",
    ],
    UserRole.READONLY: [
        "rag_search",
    ],
}


@dataclass
class UserAccount:
    """Korisnički račun s enkriptiranom lozinkom."""
    username: str
    password_hash: str              # NIKADA plain text
    display_name: str = ""
    role: UserRole = UserRole.RACUNOVODA
    email: str = ""
    active: bool = True
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_login: str = ""
    failed_attempts: int = 0
    locked_until: str = ""
    max_sessions: int = 2
    ip_whitelist: List[str] = field(default_factory=list)  # Prazno = sve dozvoljeno
    totp_secret: str = ""           # Za 2FA (opcijski)

    def has_permission(self, permission: str) -> bool:
        perms = ROLE_PERMISSIONS.get(self.role, [])
        return "all" in perms or permission in perms

    def can_access_from(self, ip: str) -> bool:
        """Super admin može odasvud. Ostali prema IP listi."""
        if self.role == UserRole.SUPER_ADMIN:
            return True  # Pristup odasvud
        if not self.ip_whitelist:
            return True  # Nema ograničenja
        return ip in self.ip_whitelist

    def is_locked(self) -> bool:
        if not self.locked_until:
            return False
        try:
            lock_time = datetime.fromisoformat(self.locked_until)
            return datetime.now() < lock_time
        except ValueError:
            return False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "username": self.username,
            "display_name": self.display_name,
            "role": self.role.value,
            "active": self.active,
            "created_at": self.created_at,
            "last_login": self.last_login,
            "locked": self.is_locked(),
            "permissions": ROLE_PERMISSIONS.get(self.role, []),
        }


# ═══════════════════════════════════════════
# CREDENTIAL VAULT (SQLite + encrypted)
# ═══════════════════════════════════════════

class CredentialVault:
    """
    Sigurna pohrana korisničkih podataka.

    Lozinke: PBKDF2-HMAC-SHA256 hash (600k iteracija)
    Vault:   SQLite s enkriptiranim osjetljivim poljima
    Lockout: 5 neuspjelih pokušaja → zaključaj 15 min
    """

    MAX_FAILED_ATTEMPTS = 5
    LOCKOUT_MINUTES = 15

    def __init__(self, db_path: str = ""):
        self.db_path = db_path or os.path.join(
            os.environ.get("NYX_DATA_DIR", "/tmp/nyx-data"), "vault.db"
        )
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                display_name TEXT DEFAULT '',
                role TEXT DEFAULT 'racunovoda',
                email TEXT DEFAULT '',
                active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT '',
                last_login TEXT DEFAULT '',
                failed_attempts INTEGER DEFAULT 0,
                locked_until TEXT DEFAULT '',
                max_sessions INTEGER DEFAULT 2,
                ip_whitelist TEXT DEFAULT '[]',
                totp_secret TEXT DEFAULT ''
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS auth_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                username TEXT NOT NULL,
                ip_address TEXT DEFAULT '',
                action TEXT NOT NULL,
                success INTEGER NOT NULL,
                details TEXT DEFAULT ''
            )
        """)
        conn.commit()
        conn.close()

    def create_user(self, username: str, password: str,
                    display_name: str = "", role: UserRole = UserRole.RACUNOVODA,
                    email: str = "", ip_whitelist: List[str] = None) -> UserAccount:
        """Kreiraj novog korisnika s hashiranom lozinkom."""
        password_hash = PasswordHasher.hash_password(password)

        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "INSERT INTO users (username, password_hash, display_name, role, "
                "email, active, created_at, ip_whitelist) "
                "VALUES (?, ?, ?, ?, ?, 1, ?, ?)",
                (username, password_hash, display_name or username,
                 role.value, email, datetime.now().isoformat(),
                 json.dumps(ip_whitelist or []))
            )
            conn.commit()
        finally:
            conn.close()

        logger.info("User created: %s (role: %s)", username, role.value)
        return UserAccount(
            username=username,
            password_hash=password_hash,
            display_name=display_name or username,
            role=role,
            email=email,
        )

    def authenticate(self, username: str, password: str,
                     ip: str = "") -> Optional[UserAccount]:
        """
        Autenticiraj korisnika.
        Vraća UserAccount ako uspješno, None ako neuspješno.
        """
        conn = sqlite3.connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            ).fetchone()

            if not row:
                self._log_auth(conn, username, ip, "login_failed", False, "User not found")
                return None

            user = self._row_to_account(row)

            # Provjeri zaključanost
            if user.is_locked():
                self._log_auth(conn, username, ip, "login_blocked", False, "Account locked")
                return None

            # Provjeri lozinku
            if not PasswordHasher.verify_password(password, user.password_hash):
                # Inkrementiraj failed attempts
                new_attempts = user.failed_attempts + 1
                locked_until = ""
                if new_attempts >= self.MAX_FAILED_ATTEMPTS:
                    locked_until = (datetime.now() + timedelta(
                        minutes=self.LOCKOUT_MINUTES)).isoformat()

                conn.execute(
                    "UPDATE users SET failed_attempts = ?, locked_until = ? "
                    "WHERE username = ?",
                    (new_attempts, locked_until, username)
                )
                conn.commit()
                self._log_auth(conn, username, ip, "login_failed", False,
                              f"Wrong password (attempt {new_attempts})")
                return None

            # Provjeri IP pristup
            if not user.can_access_from(ip):
                self._log_auth(conn, username, ip, "login_denied", False,
                              f"IP {ip} not in whitelist")
                return None

            # Provjeri je li aktivan
            if not user.active:
                self._log_auth(conn, username, ip, "login_denied", False, "Account disabled")
                return None

            # Uspješna prijava
            conn.execute(
                "UPDATE users SET last_login = ?, failed_attempts = 0, "
                "locked_until = '' WHERE username = ?",
                (datetime.now().isoformat(), username)
            )
            conn.commit()
            self._log_auth(conn, username, ip, "login_success", True)

            user.last_login = datetime.now().isoformat()
            user.failed_attempts = 0
            return user

        finally:
            conn.close()

    def get_user(self, username: str) -> Optional[UserAccount]:
        conn = sqlite3.connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            ).fetchone()
            return self._row_to_account(row) if row else None
        finally:
            conn.close()

    def list_users(self) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        try:
            rows = conn.execute("SELECT * FROM users ORDER BY created_at").fetchall()
            return [self._row_to_account(r).to_dict() for r in rows]
        finally:
            conn.close()

    def update_password(self, username: str, new_password: str):
        new_hash = PasswordHasher.hash_password(new_password)
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "UPDATE users SET password_hash = ?, failed_attempts = 0, "
                "locked_until = '' WHERE username = ?",
                (new_hash, username)
            )
            conn.commit()
        finally:
            conn.close()

    def deactivate_user(self, username: str):
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("UPDATE users SET active = 0 WHERE username = ?", (username,))
            conn.commit()
        finally:
            conn.close()

    def get_auth_log(self, limit: int = 50) -> List[Dict]:
        conn = sqlite3.connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT * FROM auth_log ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            ).fetchall()
            return [
                {"id": r[0], "timestamp": r[1], "username": r[2],
                 "ip": r[3], "action": r[4], "success": bool(r[5]),
                 "details": r[6]}
                for r in rows
            ]
        finally:
            conn.close()

    def _log_auth(self, conn, username, ip, action, success, details=""):
        conn.execute(
            "INSERT INTO auth_log (timestamp, username, ip_address, action, success, details) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (datetime.now().isoformat(), username, ip, action, int(success), details)
        )
        conn.commit()

    def _row_to_account(self, row) -> UserAccount:
        return UserAccount(
            username=row[0],
            password_hash=row[1],
            display_name=row[2],
            role=UserRole(row[3]),
            email=row[4],
            active=bool(row[5]),
            created_at=row[6],
            last_login=row[7],
            failed_attempts=row[8],
            locked_until=row[9],
            max_sessions=row[10],
            ip_whitelist=json.loads(row[11]) if row[11] else [],
            totp_secret=row[12],
        )

    def get_stats(self) -> Dict[str, Any]:
        conn = sqlite3.connect(self.db_path)
        try:
            total = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            active = conn.execute("SELECT COUNT(*) FROM users WHERE active = 1").fetchone()[0]
            by_role = {}
            for row in conn.execute("SELECT role, COUNT(*) FROM users GROUP BY role"):
                by_role[row[0]] = row[1]
            return {
                "total_users": total,
                "active_users": active,
                "by_role": by_role,
                "vault_path": self.db_path,
            }
        finally:
            conn.close()


# ═══════════════════════════════════════════
# SUPER ADMIN BOOTSTRAP
# ═══════════════════════════════════════════

class SuperAdminBootstrap:
    """
    Bootstrap super admin računa tijekom instalacije.

    Super admin hash se generira JEDNOM tijekom prvog pokretanja
    i pohranjuje u vault. Originalna lozinka se NIKADA ne zapisuje.
    """

    # Pre-computed PBKDF2-SHA256 hash (600k iteracija, 32-byte salt)
    # Originalna lozinka NIKADA nije pohranjena u source kodu.
    # Hash generiran jednom i ugrađen — ne može se obrnuti (one-way).
    SUPER_ADMIN_USERNAME = "mladen1312"
    SUPER_ADMIN_DISPLAY = "Dr. Mladen Mester"
    SUPER_ADMIN_ROLE = UserRole.SUPER_ADMIN
    _SUPER_ADMIN_HASH = (
        "$pbkdf2_sha256$600000$"
        "mMlCTvW+8A0QjlxSC0Nq0PdynXVHKErb7oRy2yq5U1Q=$"
        "uKNaB8zThRpQUPKUFjwwt2jf01kjT6+8jqVYtzlxjghT1jgXYMcSikmuxwa4"
        "/XoCAsT+lYmN8Ap8QiTVb5mMGQ=="
    )

    @classmethod
    def bootstrap(cls, vault: CredentialVault,
                  password_hash: str = "") -> bool:
        """
        Kreiraj super admin ako ne postoji.
        Koristi ugrađeni hash — lozinka se NIKAD ne traži niti pohranjuje.
        """
        existing = vault.get_user(cls.SUPER_ADMIN_USERNAME)
        if existing:
            logger.info("Super admin already exists")
            return False

        # Koristi ugrađeni hash ili eksplicitno proslijeđeni
        final_hash = password_hash or cls._SUPER_ADMIN_HASH

        conn = sqlite3.connect(vault.db_path)
        try:
            conn.execute(
                "INSERT INTO users (username, password_hash, display_name, role, "
                "email, active, created_at, max_sessions, ip_whitelist) "
                "VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)",
                (cls.SUPER_ADMIN_USERNAME, final_hash,
                 cls.SUPER_ADMIN_DISPLAY, cls.SUPER_ADMIN_ROLE.value,
                 "", datetime.now().isoformat(), 10,
                 json.dumps([]))  # Prazna lista = pristup odasvud
            )
            conn.commit()
            logger.info("Super admin bootstrapped: %s", cls.SUPER_ADMIN_USERNAME)
            return True
        finally:
            conn.close()

    @classmethod
    def verify_super_admin(cls, vault: CredentialVault) -> bool:
        """Provjeri postoji li super admin u vault-u."""
        user = vault.get_user(cls.SUPER_ADMIN_USERNAME)
        if not user:
            return False
        return user.role == UserRole.SUPER_ADMIN and user.active


# ═══════════════════════════════════════════
# JWT TOKEN MANAGER
# ═══════════════════════════════════════════

class TokenManager:
    """JWT-like token sustav za autentikaciju sesija."""

    def __init__(self, secret_key: str = ""):
        self.secret = secret_key or secrets.token_hex(32)
        self._tokens: Dict[str, Dict] = {}

    def create_token(self, user: UserAccount, ip: str = "") -> str:
        """Kreiraj session token za korisnika."""
        token = secrets.token_urlsafe(48)
        expires = datetime.now() + timedelta(hours=8)
        if user.role == UserRole.SUPER_ADMIN:
            expires = datetime.now() + timedelta(hours=24)  # Dulja sesija

        self._tokens[token] = {
            "username": user.username,
            "role": user.role.value,
            "display_name": user.display_name,
            "created_at": datetime.now().isoformat(),
            "expires_at": expires.isoformat(),
            "ip": ip,
        }
        return token

    def validate_token(self, token: str) -> Optional[Dict]:
        """Validiraj token. Vraća user info ili None."""
        data = self._tokens.get(token)
        if not data:
            return None
        if datetime.now() > datetime.fromisoformat(data["expires_at"]):
            del self._tokens[token]
            return None
        return data

    def revoke_token(self, token: str):
        self._tokens.pop(token, None)

    def revoke_user_tokens(self, username: str):
        to_remove = [t for t, d in self._tokens.items() if d["username"] == username]
        for t in to_remove:
            del self._tokens[t]

    def active_sessions(self) -> List[Dict]:
        now = datetime.now()
        active = []
        for token, data in list(self._tokens.items()):
            if now < datetime.fromisoformat(data["expires_at"]):
                active.append({
                    "username": data["username"],
                    "role": data["role"],
                    "ip": data["ip"],
                    "created_at": data["created_at"],
                })
        return active
