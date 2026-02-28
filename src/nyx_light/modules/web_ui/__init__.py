"""
Nyx Light — Web/Chat UI za 15 Zaposlenika
═══════════════════════════════════════════
Kompletno web sučelje za računovodstveni ured.

Arhitektura:
  Frontend: Single-page HTML/CSS/JS (zero build step, served by FastAPI)
  Backend:  FastAPI REST + WebSocket (src/nyx_light/api/app.py)
  Auth:     JWT token, 15 concurrent sessions
  Real-time: WebSocket za chat, SSE za notifikacije

Sučelje:
  1. Dashboard — KPI, zadnji računi, anomalije
  2. Chat — AI asistent za kontiranje i porezne upite
  3. Inbox — primljeni računi (Peppol + email + sken)
  4. Knjiženja — pregled i odobravanje prijedloga
  5. Klijenti — baza klijenata
  6. Izvještaji — GFI, PDV, JOPPD
  7. RAG — pretraga zakona
  8. Postavke — korisnici, modeli, memorija
"""

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nyx_light.ui")


# ═══════════════════════════════════════════
# UI CONFIGURATION
# ═══════════════════════════════════════════

class UITheme(str, Enum):
    LIGHT = "light"
    DARK = "dark"
    AUTO = "auto"


@dataclass
class UIConfig:
    """Konfiguracija Web UI-a."""
    app_name: str = "Nyx Light — Računovođa"
    version: str = "3.0"
    max_concurrent_users: int = 15
    session_timeout_minutes: int = 480  # 8 sati
    default_theme: UITheme = UITheme.LIGHT
    default_language: str = "hr"
    chat_max_history: int = 100
    notifications_enabled: bool = True
    auto_refresh_seconds: int = 30

    # API endpoints (relative)
    api_base: str = "/api/v1"
    ws_chat: str = "/ws/chat"
    ws_notifications: str = "/ws/notifications"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "app_name": self.app_name,
            "version": self.version,
            "max_users": self.max_concurrent_users,
            "session_timeout": self.session_timeout_minutes,
            "theme": self.default_theme.value,
            "language": self.default_language,
            "api_base": self.api_base,
            "ws_chat": self.ws_chat,
        }


# ═══════════════════════════════════════════
# SESSION MANAGER (WebSocket + REST)
# ═══════════════════════════════════════════

@dataclass
class UserSession:
    """Aktivna korisnička sesija."""
    session_id: str = ""
    user_id: str = ""
    username: str = ""
    role: str = "racunovoda"  # admin, racunovoda, pripravnik
    connected_at: str = ""
    last_activity: str = ""
    ip_address: str = ""
    user_agent: str = ""
    active_client: str = ""  # Klijent na kojem radi
    ws_connected: bool = False
    theme: UITheme = UITheme.LIGHT

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "username": self.username,
            "role": self.role,
            "connected_at": self.connected_at,
            "last_activity": self.last_activity,
            "active_client": self.active_client,
            "ws_connected": self.ws_connected,
        }


class UISessionManager:
    """Upravlja aktivnim sesijama za do 15 korisnika."""

    def __init__(self, max_sessions: int = 15):
        self.max_sessions = max_sessions
        self._sessions: Dict[str, UserSession] = {}
        self._ws_connections: Dict[str, Any] = {}  # session_id → WebSocket

    def create_session(self, user_id: str, username: str,
                       role: str = "racunovoda",
                       ip: str = "", ua: str = "") -> Optional[UserSession]:
        """Kreiraj novu sesiju (odbij ako >= max)."""
        # Provjeri postojeću sesiju za istog korisnika
        for sid, s in self._sessions.items():
            if s.user_id == user_id:
                s.last_activity = datetime.now().isoformat()
                return s

        if len(self._sessions) >= self.max_sessions:
            # Izbaci najstariju neaktivnu
            oldest = self._find_oldest_inactive()
            if oldest:
                self.close_session(oldest)
            else:
                return None  # Sve sesije aktivne

        import uuid
        session = UserSession(
            session_id=str(uuid.uuid4()),
            user_id=user_id,
            username=username,
            role=role,
            connected_at=datetime.now().isoformat(),
            last_activity=datetime.now().isoformat(),
            ip_address=ip,
            user_agent=ua,
        )
        self._sessions[session.session_id] = session
        logger.info("Session created: %s (%s) [%d/%d]",
                     username, session.session_id[:8],
                     len(self._sessions), self.max_sessions)
        return session

    def close_session(self, session_id: str):
        """Zatvori sesiju."""
        if session_id in self._sessions:
            user = self._sessions[session_id].username
            del self._sessions[session_id]
            self._ws_connections.pop(session_id, None)
            logger.info("Session closed: %s", user)

    def get_session(self, session_id: str) -> Optional[UserSession]:
        session = self._sessions.get(session_id)
        if session:
            session.last_activity = datetime.now().isoformat()
        return session

    def register_ws(self, session_id: str, ws: Any):
        """Registriraj WebSocket konekciju."""
        self._ws_connections[session_id] = ws
        if session_id in self._sessions:
            self._sessions[session_id].ws_connected = True

    def unregister_ws(self, session_id: str):
        self._ws_connections.pop(session_id, None)
        if session_id in self._sessions:
            self._sessions[session_id].ws_connected = False

    async def broadcast(self, message: Dict[str, Any], exclude: str = ""):
        """Pošalji poruku svim spojenim korisnicima."""
        for sid, ws in list(self._ws_connections.items()):
            if sid == exclude:
                continue
            try:
                if hasattr(ws, 'send_json'):
                    await ws.send_json(message)
            except Exception:
                self.unregister_ws(sid)

    def _find_oldest_inactive(self) -> Optional[str]:
        """Pronađi najstariju sesiju bez WebSocket-a."""
        oldest_id, oldest_time = None, None
        for sid, s in self._sessions.items():
            if not s.ws_connected:
                if oldest_time is None or s.last_activity < oldest_time:
                    oldest_id = sid
                    oldest_time = s.last_activity
        return oldest_id

    def get_active_sessions(self) -> List[Dict]:
        return [s.to_dict() for s in self._sessions.values()]

    def get_stats(self) -> Dict[str, Any]:
        ws_count = sum(1 for s in self._sessions.values() if s.ws_connected)
        return {
            "active_sessions": len(self._sessions),
            "max_sessions": self.max_sessions,
            "ws_connected": ws_count,
            "available_slots": self.max_sessions - len(self._sessions),
        }


# ═══════════════════════════════════════════
# NOTIFICATION SYSTEM
# ═══════════════════════════════════════════

class NotificationType(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    SUCCESS = "success"
    APPROVAL_NEEDED = "approval_needed"
    ANOMALY = "anomaly"
    DEADLINE = "deadline"


@dataclass
class Notification:
    """Notifikacija za korisnika."""
    id: str = ""
    type: NotificationType = NotificationType.INFO
    title: str = ""
    message: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    read: bool = False
    target_user: str = ""   # Prazno = svi
    action_url: str = ""    # Link na relevantnu stranicu
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "title": self.title,
            "message": self.message,
            "created_at": self.created_at,
            "read": self.read,
            "action_url": self.action_url,
        }


class NotificationManager:
    """Sustav notifikacija za ured."""

    def __init__(self, session_manager: UISessionManager = None):
        self.sessions = session_manager
        self._notifications: List[Notification] = []
        self._counter = 0

    def create(self, type: NotificationType, title: str, message: str,
               target_user: str = "", action_url: str = "",
               metadata: Dict = None) -> Notification:
        self._counter += 1
        notif = Notification(
            id=f"notif_{int(time.time()*1000)}_{self._counter:06d}",
            type=type,
            title=title,
            message=message,
            target_user=target_user,
            action_url=action_url,
            metadata=metadata or {},
        )
        self._notifications.append(notif)
        return notif

    def get_for_user(self, user_id: str, unread_only: bool = False,
                     limit: int = 50) -> List[Notification]:
        results = []
        for n in reversed(self._notifications):
            if n.target_user and n.target_user != user_id:
                continue
            if unread_only and n.read:
                continue
            results.append(n)
            if len(results) >= limit:
                break
        return results

    def mark_read(self, notif_id: str):
        for n in self._notifications:
            if n.id == notif_id:
                n.read = True
                break

    def get_unread_count(self, user_id: str) -> int:
        return len(self.get_for_user(user_id, unread_only=True))


# ═══════════════════════════════════════════
# HTML TEMPLATE GENERATOR
# ═══════════════════════════════════════════

class UITemplateGenerator:
    """
    Generira kompletno HTML/CSS/JS sučelje.
    Single-file SPA — zero build step, served by FastAPI.
    """

    @staticmethod
    def generate_index_html() -> str:
        return '''<!DOCTYPE html>
<html lang="hr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Nyx Light — Računovođa</title>
    <style>
        :root {
            --primary: #1B365D;
            --accent: #2E75B6;
            --success: #2D8B4E;
            --warning: #D4A843;
            --danger: #C0392B;
            --bg: #F5F7FA;
            --card: #FFFFFF;
            --text: #2C3E50;
            --text-light: #7F8C8D;
            --border: #E1E8ED;
            --sidebar-w: 240px;
            --header-h: 56px;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: var(--bg); color: var(--text); }

        /* ── Sidebar ── */
        .sidebar {
            position: fixed; left: 0; top: 0; bottom: 0; width: var(--sidebar-w);
            background: var(--primary); padding: 16px 0; z-index: 100;
            display: flex; flex-direction: column;
        }
        .sidebar-logo {
            padding: 0 20px 20px; border-bottom: 1px solid rgba(255,255,255,0.1);
            margin-bottom: 8px;
        }
        .sidebar-logo h1 { color: #fff; font-size: 20px; font-weight: 700; }
        .sidebar-logo span { color: var(--accent); font-size: 12px; }
        .nav-item {
            display: flex; align-items: center; padding: 10px 20px; color: rgba(255,255,255,0.7);
            cursor: pointer; transition: all 0.2s; font-size: 14px; text-decoration: none;
        }
        .nav-item:hover, .nav-item.active { background: rgba(255,255,255,0.1); color: #fff; }
        .nav-item.active { border-left: 3px solid var(--accent); }
        .nav-icon { width: 20px; margin-right: 12px; text-align: center; }
        .nav-badge {
            margin-left: auto; background: var(--danger); color: #fff; font-size: 11px;
            padding: 2px 6px; border-radius: 10px; min-width: 20px; text-align: center;
        }
        .sidebar-footer { margin-top: auto; padding: 16px 20px; border-top: 1px solid rgba(255,255,255,0.1); }
        .sidebar-footer .user-info { color: rgba(255,255,255,0.7); font-size: 13px; }
        .sidebar-footer .user-name { color: #fff; font-weight: 600; }

        /* ── Header ── */
        .header {
            position: fixed; top: 0; left: var(--sidebar-w); right: 0; height: var(--header-h);
            background: var(--card); border-bottom: 1px solid var(--border);
            display: flex; align-items: center; padding: 0 24px; z-index: 90;
        }
        .header-title { font-size: 18px; font-weight: 600; flex: 1; }
        .header-status {
            display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--text-light);
        }
        .status-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--success); }
        .status-dot.warning { background: var(--warning); }
        .status-dot.error { background: var(--danger); }

        /* ── Main Content ── */
        .main {
            margin-left: var(--sidebar-w); margin-top: var(--header-h);
            padding: 24px; min-height: calc(100vh - var(--header-h));
        }

        /* ── Cards ── */
        .card {
            background: var(--card); border-radius: 8px; padding: 20px;
            border: 1px solid var(--border); margin-bottom: 16px;
        }
        .card-title { font-size: 14px; font-weight: 600; color: var(--text-light); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 12px; }
        .card-value { font-size: 28px; font-weight: 700; color: var(--primary); }
        .card-subtitle { font-size: 13px; color: var(--text-light); margin-top: 4px; }

        /* ── Grid ── */
        .grid { display: grid; gap: 16px; }
        .grid-4 { grid-template-columns: repeat(4, 1fr); }
        .grid-3 { grid-template-columns: repeat(3, 1fr); }
        .grid-2 { grid-template-columns: repeat(2, 1fr); }
        @media (max-width: 1200px) { .grid-4 { grid-template-columns: repeat(2, 1fr); } }

        /* ── Chat Panel ── */
        .chat-container { display: flex; flex-direction: column; height: calc(100vh - var(--header-h) - 48px); }
        .chat-messages { flex: 1; overflow-y: auto; padding: 16px; }
        .chat-msg { margin-bottom: 12px; display: flex; gap: 10px; }
        .chat-msg.ai .chat-bubble { background: #EBF5FB; border: 1px solid #D4E6F1; }
        .chat-msg.user .chat-bubble { background: var(--primary); color: #fff; margin-left: auto; }
        .chat-bubble { padding: 10px 14px; border-radius: 12px; max-width: 75%; font-size: 14px; line-height: 1.5; }
        .chat-avatar { width: 32px; height: 32px; border-radius: 50%; background: var(--accent); display: flex; align-items: center; justify-content: center; color: #fff; font-size: 14px; font-weight: 600; flex-shrink: 0; }
        .chat-input-area { display: flex; gap: 8px; padding: 12px 0; border-top: 1px solid var(--border); }
        .chat-input { flex: 1; padding: 10px 14px; border: 1px solid var(--border); border-radius: 8px; font-size: 14px; outline: none; }
        .chat-input:focus { border-color: var(--accent); }
        .chat-send { padding: 10px 20px; background: var(--accent); color: #fff; border: none; border-radius: 8px; cursor: pointer; font-weight: 600; }
        .chat-send:hover { background: var(--primary); }

        /* ── Table ── */
        .data-table { width: 100%; border-collapse: collapse; font-size: 14px; }
        .data-table th { background: var(--bg); padding: 10px 12px; text-align: left; font-weight: 600; color: var(--text-light); border-bottom: 2px solid var(--border); }
        .data-table td { padding: 10px 12px; border-bottom: 1px solid var(--border); }
        .data-table tr:hover td { background: #F8FAFC; }

        /* ── Badges ── */
        .badge { display: inline-block; padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; }
        .badge-success { background: #E8F5E9; color: var(--success); }
        .badge-warning { background: #FFF8E1; color: #F57F17; }
        .badge-danger { background: #FFEBEE; color: var(--danger); }
        .badge-info { background: #E3F2FD; color: var(--accent); }

        /* ── Buttons ── */
        .btn { padding: 8px 16px; border-radius: 6px; border: none; cursor: pointer; font-size: 14px; font-weight: 500; transition: all 0.2s; }
        .btn-primary { background: var(--accent); color: #fff; }
        .btn-primary:hover { background: var(--primary); }
        .btn-success { background: var(--success); color: #fff; }
        .btn-danger { background: var(--danger); color: #fff; }
        .btn-outline { background: transparent; border: 1px solid var(--border); color: var(--text); }

        /* ── Approval Bar ── */
        .approval-bar { display: flex; gap: 8px; align-items: center; padding: 12px 16px; background: #FFF8E1; border-radius: 8px; margin-bottom: 8px; }
        .approval-bar .label { flex: 1; font-size: 14px; }

        /* ── Section visibility ── */
        .section { display: none; }
        .section.active { display: block; }

        /* ── Login overlay ── */
        .login-overlay {
            position: fixed; inset: 0; background: var(--primary); display: flex;
            align-items: center; justify-content: center; z-index: 1000;
        }
        .login-box { background: var(--card); padding: 40px; border-radius: 12px; width: 380px; }
        .login-box h2 { text-align: center; margin-bottom: 24px; color: var(--primary); }
        .login-box input { width: 100%; padding: 10px 14px; margin-bottom: 12px; border: 1px solid var(--border); border-radius: 6px; font-size: 14px; }
        .login-box .btn { width: 100%; padding: 12px; font-size: 16px; }
        .login-error { color: var(--danger); font-size: 13px; text-align: center; margin-bottom: 8px; }
    </style>
</head>
<body>
    <!-- ══════ LOGIN ══════ -->
    <div id="login-overlay" class="login-overlay">
        <div class="login-box">
            <h2>Nyx Light — Računovođa</h2>
            <div id="login-error" class="login-error" style="display:none;"></div>
            <input id="login-user" type="text" placeholder="Korisničko ime" autofocus>
            <input id="login-pass" type="password" placeholder="Lozinka">
            <button class="btn btn-primary" onclick="doLogin()">Prijava</button>
            <p style="text-align:center;margin-top:12px;font-size:12px;color:#999;">v3.0 — 100% lokalno</p>
        </div>
    </div>

    <!-- ══════ SIDEBAR ══════ -->
    <nav class="sidebar" id="sidebar" style="display:none;">
        <div class="sidebar-logo">
            <h1>Nyx Light</h1>
            <span>Računovođa v3.0</span>
        </div>
        <a class="nav-item active" data-section="dashboard" onclick="showSection(this)">
            <span class="nav-icon">📊</span> Dashboard
        </a>
        <a class="nav-item" data-section="chat" onclick="showSection(this)">
            <span class="nav-icon">💬</span> AI Chat
        </a>
        <a class="nav-item" data-section="inbox" onclick="showSection(this)">
            <span class="nav-icon">📥</span> Inbox
            <span class="nav-badge" id="inbox-badge" style="display:none;">0</span>
        </a>
        <a class="nav-item" data-section="knjizenja" onclick="showSection(this)">
            <span class="nav-icon">📋</span> Knjiženja
        </a>
        <a class="nav-item" data-section="klijenti" onclick="showSection(this)">
            <span class="nav-icon">👥</span> Klijenti
        </a>
        <a class="nav-item" data-section="izvjestaji" onclick="showSection(this)">
            <span class="nav-icon">📈</span> Izvještaji
        </a>
        <a class="nav-item" data-section="zakoni" onclick="showSection(this)">
            <span class="nav-icon">⚖️</span> Zakoni (RAG)
        </a>
        <a class="nav-item" data-section="postavke" onclick="showSection(this)">
            <span class="nav-icon">⚙️</span> Postavke
        </a>
        <div class="sidebar-footer">
            <div class="user-info">
                <div class="user-name" id="sidebar-user">—</div>
                <div style="font-size:12px;margin-top:2px;" id="sidebar-role">—</div>
            </div>
            <button class="btn btn-outline" style="margin-top:8px;width:100%;font-size:12px;" onclick="doLogout()">Odjava</button>
        </div>
    </nav>

    <!-- ══════ HEADER ══════ -->
    <header class="header" id="header" style="display:none;">
        <div class="header-title" id="header-title">Dashboard</div>
        <div class="header-status">
            <span class="status-dot" id="ai-status"></span>
            <span id="ai-status-text">AI aktivan</span>
            &nbsp;|&nbsp;
            <span id="active-users">0/15 korisnika</span>
        </div>
    </header>

    <!-- ══════ MAIN CONTENT ══════ -->
    <main class="main" id="main" style="display:none;">

        <!-- Dashboard -->
        <div class="section active" id="sec-dashboard">
            <div class="grid grid-4">
                <div class="card"><div class="card-title">Danas obrađeno</div><div class="card-value" id="kpi-today">0</div><div class="card-subtitle">računa</div></div>
                <div class="card"><div class="card-title">Čeka odobrenje</div><div class="card-value" id="kpi-pending">0</div><div class="card-subtitle">knjiženja</div></div>
                <div class="card"><div class="card-title">Anomalije</div><div class="card-value" id="kpi-anomalies">0</div><div class="card-subtitle">upozorenja</div></div>
                <div class="card"><div class="card-title">AI pouzdanost</div><div class="card-value" id="kpi-confidence">—</div><div class="card-subtitle">prosječna</div></div>
            </div>
            <div class="grid grid-2" style="margin-top:16px;">
                <div class="card">
                    <div class="card-title">Zadnji računi</div>
                    <table class="data-table" id="recent-invoices">
                        <thead><tr><th>Dobavljač</th><th>Iznos</th><th>Status</th></tr></thead>
                        <tbody><tr><td colspan="3" style="text-align:center;color:#999;">Učitavanje...</td></tr></tbody>
                    </table>
                </div>
                <div class="card">
                    <div class="card-title">Rokovi</div>
                    <table class="data-table" id="deadlines-table">
                        <thead><tr><th>Rok</th><th>Opis</th><th>Dana</th></tr></thead>
                        <tbody><tr><td colspan="3" style="text-align:center;color:#999;">Učitavanje...</td></tr></tbody>
                    </table>
                </div>
            </div>
        </div>

        <!-- Chat -->
        <div class="section" id="sec-chat">
            <div class="card chat-container">
                <div class="chat-messages" id="chat-messages">
                    <div class="chat-msg ai">
                        <div class="chat-avatar">N</div>
                        <div class="chat-bubble">Pozdrav! Ja sam Nyx, vaš AI asistent za računovodstvo. Pitajte me o kontiranju, porezima, zakonima — ili mi pošaljite sliku računa za obradu.</div>
                    </div>
                </div>
                <div class="chat-input-area">
                    <input class="chat-input" id="chat-input" placeholder="Unesite poruku ili pitanje..." onkeydown="if(event.key==='Enter')sendChat()">
                    <button class="chat-send" onclick="sendChat()">Pošalji</button>
                </div>
            </div>
        </div>

        <!-- Inbox -->
        <div class="section" id="sec-inbox">
            <div class="card">
                <div class="card-title">Primljeni računi</div>
                <div style="margin-bottom:12px;">
                    <button class="btn btn-primary" onclick="refreshInbox()">Osvježi</button>
                    <button class="btn btn-outline" style="margin-left:8px;">Filter</button>
                </div>
                <table class="data-table" id="inbox-table">
                    <thead><tr><th>Datum</th><th>Pošiljatelj</th><th>Iznos</th><th>Tier</th><th>Status</th><th>Akcija</th></tr></thead>
                    <tbody><tr><td colspan="6" style="text-align:center;color:#999;">Nema novih računa</td></tr></tbody>
                </table>
            </div>
        </div>

        <!-- Knjiženja -->
        <div class="section" id="sec-knjizenja">
            <div class="card">
                <div class="card-title">Prijedlozi knjiženja za odobrenje</div>
                <div id="approval-list">
                    <div class="approval-bar">
                        <div class="label">
                            <strong>R-001/2026 | Dobavljač ABC d.o.o.</strong><br>
                            <span style="color:#999;font-size:13px;">Konto 4210 — Uredski materijal | 1.250,00 EUR (PDV 250,00)</span>
                        </div>
                        <button class="btn btn-success btn-sm">✓ Odobri</button>
                        <button class="btn btn-outline btn-sm">✎ Ispravi</button>
                        <button class="btn btn-danger btn-sm">✗ Odbij</button>
                    </div>
                </div>
            </div>
        </div>

        <!-- Klijenti -->
        <div class="section" id="sec-klijenti">
            <div class="card">
                <div class="card-title">Baza klijenata</div>
                <table class="data-table"><thead><tr><th>Naziv</th><th>OIB</th><th>Tip</th><th>ERP</th></tr></thead>
                <tbody><tr><td>Demo d.o.o.</td><td>12345678903</td><td>d.o.o.</td><td>CPP</td></tr></tbody></table>
            </div>
        </div>

        <!-- Izvještaji -->
        <div class="section" id="sec-izvjestaji">
            <div class="card">
                <div class="card-title">Financijski izvještaji</div>
                <div class="grid grid-3">
                    <div class="card" style="cursor:pointer;text-align:center;">
                        <div style="font-size:32px;">📊</div><div style="margin-top:8px;font-weight:600;">GFI</div>
                        <div style="font-size:12px;color:#999;">Godišnji financijski izvještaj</div>
                    </div>
                    <div class="card" style="cursor:pointer;text-align:center;">
                        <div style="font-size:32px;">💰</div><div style="margin-top:8px;font-weight:600;">PDV (PPO)</div>
                        <div style="font-size:12px;color:#999;">Prijava PDV-a</div>
                    </div>
                    <div class="card" style="cursor:pointer;text-align:center;">
                        <div style="font-size:32px;">👥</div><div style="margin-top:8px;font-weight:600;">JOPPD</div>
                        <div style="font-size:12px;color:#999;">Obrazac za plaće</div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Zakoni (RAG) -->
        <div class="section" id="sec-zakoni">
            <div class="card">
                <div class="card-title">Pretraga zakona RH (Time-Aware RAG)</div>
                <div style="display:flex;gap:8px;margin-bottom:16px;">
                    <input class="chat-input" id="rag-query" placeholder="Npr. Kolika je stopa PDV-a na restoranski račun?" style="flex:1;">
                    <input class="chat-input" id="rag-date" type="date" style="width:160px;" placeholder="Datum događaja">
                    <button class="btn btn-primary" onclick="searchLaw()">Pretraži</button>
                </div>
                <div id="rag-results" style="min-height:100px;"></div>
            </div>
        </div>

        <!-- Postavke -->
        <div class="section" id="sec-postavke">
            <div class="grid grid-2">
                <div class="card">
                    <div class="card-title">AI Model Status</div>
                    <table class="data-table" id="model-status">
                        <thead><tr><th>Model</th><th>RAM</th><th>Status</th></tr></thead>
                        <tbody>
                            <tr><td>Qwen3-235B-A22B</td><td>128 GB</td><td><span class="badge badge-success">Aktivan</span></td></tr>
                            <tr><td>Qwen2.5-VL-72B</td><td>42 GB</td><td><span class="badge badge-success">Aktivan</span></td></tr>
                            <tr><td>bge-m3</td><td>1.2 GB</td><td><span class="badge badge-success">Aktivan</span></td></tr>
                        </tbody>
                    </table>
                </div>
                <div class="card">
                    <div class="card-title">Memory System</div>
                    <table class="data-table">
                        <thead><tr><th>Tier</th><th>Zapisa</th><th>Opis</th></tr></thead>
                        <tbody>
                            <tr><td>L0 (Working)</td><td id="mem-l0">—</td><td>Sesijski kontekst</td></tr>
                            <tr><td>L1 (Episodic)</td><td id="mem-l1">—</td><td>Dnevnik interakcija</td></tr>
                            <tr><td>L2 (Semantic)</td><td id="mem-l2">—</td><td>Trajna pravila</td></tr>
                            <tr><td>L3 (DPO)</td><td id="mem-l3">—</td><td>Noćna optimizacija</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>
            <div class="card">
                <div class="card-title">Aktivni korisnici</div>
                <table class="data-table" id="sessions-table">
                    <thead><tr><th>Korisnik</th><th>Uloga</th><th>Spojeno</th><th>WebSocket</th></tr></thead>
                    <tbody></tbody>
                </table>
            </div>
        </div>
    </main>

    <script>
    // ══════════════════════════════════════════
    // NYX LIGHT — FRONTEND LOGIC
    // ══════════════════════════════════════════

    const API = window.location.origin + "/api/v1";
    let token = null;
    let ws = null;
    let currentUser = null;

    // ── Login/Logout ──
    async function doLogin() {
        const user = document.getElementById("login-user").value;
        const pass = document.getElementById("login-pass").value;
        try {
            const resp = await fetch(API + "/auth/login", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({username: user, password: pass}),
            });
            if (!resp.ok) throw new Error("Pogrešni podaci");
            const data = await resp.json();
            token = data.token;
            currentUser = data.user;
            document.getElementById("login-overlay").style.display = "none";
            document.getElementById("sidebar").style.display = "flex";
            document.getElementById("header").style.display = "flex";
            document.getElementById("main").style.display = "block";
            document.getElementById("sidebar-user").textContent = currentUser.username || user;
            document.getElementById("sidebar-role").textContent = currentUser.role || "računovođa";
            connectWebSocket();
            loadDashboard();
        } catch (e) {
            const err = document.getElementById("login-error");
            err.textContent = e.message;
            err.style.display = "block";
        }
    }
    function doLogout() {
        token = null;
        if (ws) ws.close();
        document.getElementById("login-overlay").style.display = "flex";
        document.getElementById("sidebar").style.display = "none";
        document.getElementById("header").style.display = "none";
        document.getElementById("main").style.display = "none";
    }

    // ── Navigation ──
    function showSection(el) {
        document.querySelectorAll(".nav-item").forEach(n => n.classList.remove("active"));
        document.querySelectorAll(".section").forEach(s => s.classList.remove("active"));
        el.classList.add("active");
        const sec = el.dataset.section;
        document.getElementById("sec-" + sec).classList.add("active");
        document.getElementById("header-title").textContent =
            {dashboard:"Dashboard", chat:"AI Chat", inbox:"Inbox", knjizenja:"Knjiženja",
             klijenti:"Klijenti", izvjestaji:"Izvještaji", zakoni:"Zakoni (RAG)", postavke:"Postavke"}[sec] || sec;
    }

    // ── WebSocket ──
    function connectWebSocket() {
        const proto = location.protocol === "https:" ? "wss:" : "ws:";
        ws = new WebSocket(proto + "//" + location.host + "/ws/chat?token=" + token);
        ws.onmessage = (e) => {
            const msg = JSON.parse(e.data);
            if (msg.type === "chat_response") appendChat("ai", msg.content);
            if (msg.type === "notification") showNotification(msg);
        };
        ws.onclose = () => setTimeout(connectWebSocket, 3000);
    }

    // ── Chat ──
    function sendChat() {
        const input = document.getElementById("chat-input");
        const text = input.value.trim();
        if (!text) return;
        appendChat("user", text);
        input.value = "";
        if (ws && ws.readyState === 1) {
            ws.send(JSON.stringify({type: "chat", content: text}));
        } else {
            // REST fallback
            fetch(API + "/chat", {
                method: "POST",
                headers: {"Content-Type": "application/json", "Authorization": "Bearer " + token},
                body: JSON.stringify({message: text}),
            }).then(r => r.json()).then(data => appendChat("ai", data.response));
        }
    }
    function appendChat(role, text) {
        const div = document.getElementById("chat-messages");
        const avatar = role === "ai" ? "N" : currentUser?.username?.[0]?.toUpperCase() || "K";
        div.innerHTML += `<div class="chat-msg ${role}"><div class="chat-avatar">${avatar}</div><div class="chat-bubble">${escapeHtml(text)}</div></div>`;
        div.scrollTop = div.scrollHeight;
    }

    // ── RAG Search ──
    async function searchLaw() {
        const query = document.getElementById("rag-query").value;
        const eventDate = document.getElementById("rag-date").value;
        const results = document.getElementById("rag-results");
        results.innerHTML = "<p>Pretražujem...</p>";
        try {
            const resp = await fetch(API + "/rag/search", {
                method: "POST",
                headers: {"Content-Type": "application/json", "Authorization": "Bearer " + token},
                body: JSON.stringify({query, event_date: eventDate}),
            });
            const data = await resp.json();
            let html = "<div class='card' style='background:#EBF5FB;border-color:#D4E6F1;'>";
            html += "<strong>Odgovor:</strong><br>" + escapeHtml(data.answer || "Nema rezultata") + "</div>";
            if (data.citations) {
                html += "<div style='margin-top:8px;font-size:13px;color:#666;'><strong>Izvori:</strong> " + data.citations.join("; ") + "</div>";
            }
            results.innerHTML = html;
        } catch (e) { results.innerHTML = "<p style='color:red;'>Greška: " + e.message + "</p>"; }
    }

    // ── Dashboard ──
    async function loadDashboard() {
        try {
            const resp = await fetch(API + "/dashboard", {headers: {"Authorization": "Bearer " + token}});
            const data = await resp.json();
            if (data.today_processed !== undefined) document.getElementById("kpi-today").textContent = data.today_processed;
            if (data.pending_approvals !== undefined) document.getElementById("kpi-pending").textContent = data.pending_approvals;
        } catch(e) {}
    }

    // ── Utility ──
    function escapeHtml(t) { const d = document.createElement("div"); d.textContent = t; return d.innerHTML; }
    function showNotification(msg) { console.log("Notification:", msg); }
    function refreshInbox() { /* fetch inbox */ }

    // Auto-login with Enter key
    document.getElementById("login-pass").addEventListener("keydown", (e) => { if (e.key === "Enter") doLogin(); });
    </script>
</body>
</html>'''

    @staticmethod
    def generate_login_page() -> str:
        """Standalone login page (redirect ako nema sesije)."""
        return '<html><body><script>window.location="/";</script></body></html>'


# ═══════════════════════════════════════════
# API ROUTES GENERATOR
# ═══════════════════════════════════════════

class UIAPIRoutes:
    """
    Definicija API ruta za UI.
    Ove rute se registriraju u FastAPI app-u.
    """

    ROUTES = [
        # Auth
        {"method": "POST", "path": "/api/v1/auth/login", "handler": "login",
         "desc": "JWT prijava"},
        {"method": "POST", "path": "/api/v1/auth/logout", "handler": "logout",
         "desc": "Odjava i zatvaranje sesije"},

        # Dashboard
        {"method": "GET", "path": "/api/v1/dashboard", "handler": "get_dashboard",
         "desc": "KPI i pregled"},

        # Chat
        {"method": "POST", "path": "/api/v1/chat", "handler": "chat",
         "desc": "REST chat fallback"},
        {"method": "WS", "path": "/ws/chat", "handler": "ws_chat",
         "desc": "WebSocket real-time chat"},

        # Inbox
        {"method": "GET", "path": "/api/v1/inbox", "handler": "get_inbox",
         "desc": "Lista primljenih računa"},
        {"method": "POST", "path": "/api/v1/inbox/upload", "handler": "upload_invoice",
         "desc": "Upload skena/PDF-a"},

        # Knjiženja
        {"method": "GET", "path": "/api/v1/entries/pending", "handler": "get_pending",
         "desc": "Prijedlozi za odobrenje"},
        {"method": "POST", "path": "/api/v1/entries/{id}/approve", "handler": "approve",
         "desc": "Odobri knjiženje"},
        {"method": "POST", "path": "/api/v1/entries/{id}/correct", "handler": "correct",
         "desc": "Ispravi i odobri"},
        {"method": "POST", "path": "/api/v1/entries/{id}/reject", "handler": "reject",
         "desc": "Odbij prijedlog"},

        # RAG
        {"method": "POST", "path": "/api/v1/rag/search", "handler": "rag_search",
         "desc": "Pretraga zakona"},

        # Reports
        {"method": "GET", "path": "/api/v1/reports/gfi", "handler": "get_gfi",
         "desc": "GFI izvještaj"},
        {"method": "GET", "path": "/api/v1/reports/pdv", "handler": "get_pdv",
         "desc": "PDV prijava"},

        # System
        {"method": "GET", "path": "/api/v1/system/health", "handler": "health",
         "desc": "Status sustava"},
        {"method": "GET", "path": "/api/v1/system/sessions", "handler": "sessions",
         "desc": "Aktivne sesije"},
        {"method": "GET", "path": "/api/v1/system/memory", "handler": "memory_stats",
         "desc": "Memory tier status"},
    ]

    @classmethod
    def get_routes(cls) -> List[Dict[str, str]]:
        return cls.ROUTES

    @classmethod
    def get_openapi_summary(cls) -> Dict[str, Any]:
        return {
            "title": "Nyx Light API",
            "version": "3.0",
            "total_routes": len(cls.ROUTES),
            "categories": {
                "auth": 2, "dashboard": 1, "chat": 2,
                "inbox": 2, "entries": 3, "rag": 1,
                "reports": 2, "system": 3,
            },
        }
