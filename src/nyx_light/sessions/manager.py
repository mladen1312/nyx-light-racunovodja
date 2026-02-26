"""
Nyx Light — Session Manager za 15 korisnika

Upravlja sesijama zaposlenika, prati aktivnost,
i čuva kontekst razgovora po korisniku.
"""

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nyx_light.sessions")

MAX_SESSIONS = 15
SESSION_TIMEOUT_MIN = 60  # Auto-logout nakon 60 min neaktivnosti


@dataclass
class UserSession:
    """Sesija jednog korisnika."""
    session_id: str
    user_id: str
    user_name: str
    created_at: datetime
    last_active: datetime
    active_client_id: str = ""  # Klijent na kojem radi
    message_count: int = 0
    bookings_proposed: int = 0
    bookings_approved: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        return (datetime.now() - self.last_active) > timedelta(minutes=SESSION_TIMEOUT_MIN)

    def touch(self):
        self.last_active = datetime.now()


class SessionManager:
    """Upravlja sesijama 15 zaposlenika."""

    def __init__(self, max_sessions: int = MAX_SESSIONS):
        self.max_sessions = max_sessions
        self._sessions: Dict[str, UserSession] = {}
        self._by_user: Dict[str, str] = {}  # user_id → session_id
        logger.info("SessionManager: max %d sesija", max_sessions)

    def create_session(self, user_id: str, user_name: str = "") -> Optional[UserSession]:
        """Kreiraj novu sesiju za korisnika."""
        # Cleanup expired
        self._cleanup_expired()

        # Već ima sesiju?
        if user_id in self._by_user:
            existing = self._sessions.get(self._by_user[user_id])
            if existing and not existing.is_expired:
                existing.touch()
                return existing
            # Expired — ukloni
            self.end_session(self._by_user[user_id])

        # Provjeri limit
        if len(self._sessions) >= self.max_sessions:
            logger.warning(
                "Maksimalni broj sesija (%d) dosegnut! Korisnik %s ne može se spojiti.",
                self.max_sessions, user_id,
            )
            return None

        session = UserSession(
            session_id=str(uuid.uuid4()),
            user_id=user_id,
            user_name=user_name or user_id,
            created_at=datetime.now(),
            last_active=datetime.now(),
        )

        self._sessions[session.session_id] = session
        self._by_user[user_id] = session.session_id
        logger.info("Nova sesija: %s (%s)", user_name or user_id, session.session_id[:8])
        return session

    def get_session(self, session_id: str) -> Optional[UserSession]:
        """Dohvati sesiju po ID-u."""
        session = self._sessions.get(session_id)
        if session and not session.is_expired:
            session.touch()
            return session
        return None

    def get_session_by_user(self, user_id: str) -> Optional[UserSession]:
        """Dohvati sesiju po korisniku."""
        sid = self._by_user.get(user_id)
        if sid:
            return self.get_session(sid)
        return None

    def end_session(self, session_id: str):
        """Zatvori sesiju."""
        session = self._sessions.pop(session_id, None)
        if session:
            self._by_user.pop(session.user_id, None)
            logger.info("Sesija zatvorena: %s", session.user_name)

    def set_active_client(self, session_id: str, client_id: str):
        """Postavi aktivnog klijenta za sesiju."""
        session = self._sessions.get(session_id)
        if session:
            session.active_client_id = client_id
            session.touch()

    def record_message(self, session_id: str):
        """Zabilježi poruku u sesiji."""
        session = self._sessions.get(session_id)
        if session:
            session.message_count += 1
            session.touch()

    def record_booking(self, session_id: str, approved: bool = False):
        """Zabilježi predloženo/odobreno knjiženje."""
        session = self._sessions.get(session_id)
        if session:
            session.bookings_proposed += 1
            if approved:
                session.bookings_approved += 1
            session.touch()

    def _cleanup_expired(self):
        """Ukloni istekle sesije."""
        expired = [
            sid for sid, s in self._sessions.items()
            if s.is_expired
        ]
        for sid in expired:
            self.end_session(sid)
        if expired:
            logger.info("Uklonjeno %d isteklih sesija", len(expired))

    def get_active_sessions(self) -> List[Dict[str, Any]]:
        """Dohvati sve aktivne sesije."""
        self._cleanup_expired()
        return [
            {
                "session_id": s.session_id[:8] + "...",
                "user_name": s.user_name,
                "active_client": s.active_client_id,
                "messages": s.message_count,
                "bookings": f"{s.bookings_approved}/{s.bookings_proposed}",
                "idle_min": int((datetime.now() - s.last_active).total_seconds() / 60),
            }
            for s in self._sessions.values()
        ]

    def get_stats(self) -> Dict[str, Any]:
        self._cleanup_expired()
        return {
            "active_sessions": len(self._sessions),
            "max_sessions": self.max_sessions,
            "capacity_pct": round(len(self._sessions) / self.max_sessions * 100, 1),
            "total_messages": sum(s.message_count for s in self._sessions.values()),
            "total_bookings_proposed": sum(s.bookings_proposed for s in self._sessions.values()),
            "total_bookings_approved": sum(s.bookings_approved for s in self._sessions.values()),
        }
