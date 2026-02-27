"""
Nyx Light — WebSocket Notification System

Real-time notifikacije za 15 zaposlenika:
  - Nova knjiženja za odobrenje
  - Rokovi (PDV, JOPPD, GFI)
  - Završen DPO trening
  - Upozorenja (AML, limit gotovine)
  - Status AI modela
  - Upload procesiran

Svaki korisnik prima samo svoje notifikacije + broadcast za timske.
"""

import asyncio
import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger("nyx_light.notifications")


@dataclass
class Notification:
    """Jedna notifikacija."""
    id: str = ""
    type: str = "info"        # info, warning, error, success, deadline, booking
    title: str = ""
    message: str = ""
    target: str = "broadcast"  # broadcast, user:<username>, role:<role>
    module: str = ""
    data: Dict = field(default_factory=dict)
    timestamp: float = 0.0
    read: bool = False
    priority: str = "normal"   # low, normal, high, urgent

    def __post_init__(self):
        if not self.id:
            self.id = f"notif_{int(time.time()*1000)}_{id(self) % 10000}"
        if not self.timestamp:
            self.timestamp = time.time()

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "type": self.type,
            "title": self.title,
            "message": self.message,
            "module": self.module,
            "data": self.data,
            "timestamp": self.timestamp,
            "time_hr": datetime.fromtimestamp(self.timestamp).strftime("%H:%M:%S"),
            "priority": self.priority,
            "read": self.read,
        }


class NotificationManager:
    """Upravlja notifikacijama za sve korisnike."""

    def __init__(self, max_per_user: int = 100):
        self._connections: Dict[str, List] = defaultdict(list)  # username → [ws1, ws2...]
        self._notifications: Dict[str, List[Notification]] = defaultdict(list)  # user → [notifs]
        self._broadcast_history: List[Notification] = []
        self._max_per_user = max_per_user
        self._callbacks: List[Callable] = []
        self._stats = {"sent": 0, "broadcast": 0, "connections": 0}

    # ── Connection Management ──

    async def register(self, username: str, ws) -> None:
        """Registriraj WebSocket konekciju za korisnika."""
        self._connections[username].append(ws)
        self._stats["connections"] = sum(len(v) for v in self._connections.values())
        logger.info(f"WS connected: {username} (total: {self._stats['connections']})")

        # Pošalji nepročitane notifikacije
        unread = [n for n in self._notifications[username] if not n.read]
        if unread:
            await self._send_ws(ws, {
                "type": "unread_notifications",
                "notifications": [n.to_dict() for n in unread[-20:]],
            })

    async def unregister(self, username: str, ws) -> None:
        """Ukloni WebSocket konekciju."""
        if ws in self._connections[username]:
            self._connections[username].remove(ws)
        if not self._connections[username]:
            del self._connections[username]
        self._stats["connections"] = sum(len(v) for v in self._connections.values())
        logger.info(f"WS disconnected: {username}")

    # ── Send Notifications ──

    async def notify(self, notification: Notification) -> None:
        """Pošalji notifikaciju prema target pravilu."""
        target = notification.target

        if target == "broadcast":
            await self._broadcast(notification)
        elif target.startswith("user:"):
            username = target[5:]
            await self._send_to_user(username, notification)
        elif target.startswith("role:"):
            role = target[5:]
            await self._send_to_role(role, notification)
        else:
            await self._broadcast(notification)

        self._stats["sent"] += 1

        # Callbacks
        for cb in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(notification)
                else:
                    cb(notification)
            except Exception as e:
                logger.error(f"Notification callback error: {e}")

    async def notify_booking_pending(self, booking_id: str, client_name: str,
                                     description: str, assigned_to: str = "") -> None:
        """Notificiraj o novom knjiženju za odobrenje."""
        target = f"user:{assigned_to}" if assigned_to else "role:accountant"
        await self.notify(Notification(
            type="booking",
            title="Novo knjiženje za odobrenje",
            message=f"{client_name}: {description}",
            target=target,
            module="kontiranje",
            data={"booking_id": booking_id},
            priority="normal",
        ))

    async def notify_deadline(self, title: str, days_remaining: int,
                              deadline_date: str) -> None:
        """Notificiraj o roku."""
        priority = "urgent" if days_remaining <= 1 else "high" if days_remaining <= 3 else "normal"
        ntype = "warning" if days_remaining <= 3 else "deadline"
        await self.notify(Notification(
            type=ntype,
            title=f"⏰ Rok: {title}",
            message=f"Preostalo {days_remaining} dana (rok: {deadline_date})",
            target="broadcast",
            module="deadlines",
            data={"deadline": deadline_date, "days": days_remaining},
            priority=priority,
        ))

    async def notify_upload_processed(self, username: str, filename: str,
                                      result: str) -> None:
        """Notificiraj korisnika da je upload obrađen."""
        await self.notify(Notification(
            type="success" if "ok" in result.lower() else "warning",
            title="Upload obrađen",
            message=f"{filename}: {result}",
            target=f"user:{username}",
            module="upload",
            priority="normal",
        ))

    async def notify_dpo_complete(self, pairs_trained: int, improvement: float) -> None:
        """Notificiraj da je noćni DPO trening završen."""
        await self.notify(Notification(
            type="success",
            title="🧠 DPO trening završen",
            message=f"Trenirano {pairs_trained} parova, poboljšanje: {improvement:.1%}",
            target="role:admin",
            module="dpo",
            priority="low",
        ))

    async def notify_aml_warning(self, client_name: str, reason: str) -> None:
        """AML upozorenje — visokog prioriteta."""
        await self.notify(Notification(
            type="error",
            title="🚨 AML Upozorenje",
            message=f"{client_name}: {reason}",
            target="role:admin",
            module="safety",
            priority="urgent",
        ))

    # ── Internals ──

    async def _broadcast(self, notification: Notification) -> None:
        """Pošalji svim spojenim korisnicima."""
        self._broadcast_history.append(notification)
        if len(self._broadcast_history) > 200:
            self._broadcast_history = self._broadcast_history[-100:]

        msg = {"type": "notification", "notification": notification.to_dict()}
        for username, connections in self._connections.items():
            self._notifications[username].append(notification)
            self._trim_notifications(username)
            for ws in connections:
                await self._send_ws(ws, msg)

        self._stats["broadcast"] += 1

    async def _send_to_user(self, username: str, notification: Notification) -> None:
        """Pošalji jednom korisniku."""
        self._notifications[username].append(notification)
        self._trim_notifications(username)

        msg = {"type": "notification", "notification": notification.to_dict()}
        for ws in self._connections.get(username, []):
            await self._send_ws(ws, msg)

    async def _send_to_role(self, role: str, notification: Notification) -> None:
        """Pošalji svima s određenom ulogom (zahtijeva role lookup)."""
        # Za sada broadcast — u produkciji: lookup user roles
        await self._broadcast(notification)

    async def _send_ws(self, ws, data: Dict) -> None:
        """Sigurno pošalji JSON putem WebSocket."""
        try:
            if hasattr(ws, 'send_json'):
                await ws.send_json(data)
            elif hasattr(ws, 'send_text'):
                await ws.send_text(json.dumps(data, default=str))
        except Exception as e:
            logger.debug(f"WS send failed: {e}")

    def _trim_notifications(self, username: str) -> None:
        """Ograniči broj notifikacija po korisniku."""
        if len(self._notifications[username]) > self._max_per_user:
            self._notifications[username] = self._notifications[username][-self._max_per_user:]

    # ── API ──

    def get_unread(self, username: str) -> List[Dict]:
        """Dohvati nepročitane notifikacije."""
        return [n.to_dict() for n in self._notifications[username] if not n.read]

    def get_all(self, username: str, limit: int = 50) -> List[Dict]:
        """Dohvati sve notifikacije korisnika."""
        return [n.to_dict() for n in self._notifications[username][-limit:]]

    def mark_read(self, username: str, notification_id: str) -> bool:
        """Označi notifikaciju kao pročitanu."""
        for n in self._notifications[username]:
            if n.id == notification_id:
                n.read = True
                return True
        return False

    def mark_all_read(self, username: str) -> int:
        """Označi sve kao pročitane."""
        count = 0
        for n in self._notifications[username]:
            if not n.read:
                n.read = True
                count += 1
        return count

    def on_notification(self, callback: Callable) -> None:
        """Registriraj callback za svaku notifikaciju."""
        self._callbacks.append(callback)

    def get_stats(self) -> Dict[str, Any]:
        return {
            **self._stats,
            "users_connected": list(self._connections.keys()),
            "total_stored": sum(len(v) for v in self._notifications.values()),
        }
