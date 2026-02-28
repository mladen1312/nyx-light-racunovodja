"""
Nyx Light — Uredska Mreža i Pristup Djelatnika
════════════════════════════════════════════════
Kako se 15 djelatnika spaja na AI sustav u uredskom okruženju.

Mrežna arhitektura:
  ┌─────────────────────────────────────────────┐
  │              UREDSKA MREŽA (LAN)            │
  │                                             │
  │  ┌──────────┐    ┌──────────┐              │
  │  │ Računalo  │    │ Računalo  │  ← djelatnici│
  │  │ (Chrome)  │    │ (Safari)  │    koriste   │
  │  └────┬─────┘    └────┬─────┘    preglednik │
  │       │               │                     │
  │       └───────┬───────┘                     │
  │               │ HTTP :8420                  │
  │         ┌─────┴──────┐                      │
  │         │ Mac Studio  │  ← AI server        │
  │         │ 256 GB RAM  │    (nyx-studio)     │
  │         │ :8420 API   │                     │
  │         │ :8422 MLX   │                     │
  │         └─────────────┘                     │
  │               │                             │
  │         ┌─────┴──────┐                      │
  │         │  Tailscale  │  ← remote pristup   │
  │         │  (VPN mesh) │    (od kuće/terena) │
  │         └─────────────┘                     │
  └─────────────────────────────────────────────┘

Tri načina pristupa:
  1. LAN (u uredu):      http://nyx-studio.local:8420
  2. Tailscale (remote):  http://nyx-studio:8420
  3. SSH (administrator): ssh nyx@nyx-studio

Zahtjevi za djelatnike:
  - Web preglednik (Chrome, Safari, Firefox, Edge)
  - Na istoj mreži ILI Tailscale instaliran
  - Korisničko ime i lozinka (dodjeljuje admin)
"""

import hashlib
import ipaddress
import json
import logging
import os
import platform
import socket
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("nyx_light.network")


# ═══════════════════════════════════════════
# MREŽNA KONFIGURACIJA
# ═══════════════════════════════════════════

class AccessMethod(str, Enum):
    """Način pristupa sustavu."""
    LAN = "lan"                # Uredska mreža (Ethernet/WiFi)
    TAILSCALE = "tailscale"    # VPN mesh (remote)
    SSH = "ssh"                # Terminal (admin only)
    LOCALHOST = "localhost"    # Direktno na Mac Studiju


@dataclass
class NetworkConfig:
    """Mrežna konfiguracija Mac Studio servera."""
    # Hostname
    hostname: str = "nyx-studio"
    mdns_name: str = "nyx-studio.local"  # Bonjour/mDNS

    # Portovi
    api_port: int = 8420           # FastAPI (Web UI + REST API)
    mlx_port: int = 8422           # MLX LLM server (internal only)
    ws_port: int = 8420            # WebSocket (isti kao API)

    # Mrežni interfejsi
    bind_address: str = "0.0.0.0"  # Sluša na svim interfejsima
    mlx_bind: str = "127.0.0.1"   # MLX samo lokalno (sigurnost)

    # Tailscale
    tailscale_hostname: str = "nyx-studio"
    tailscale_enabled: bool = True

    # SSL/TLS (opcijski za HTTPS)
    ssl_enabled: bool = False
    ssl_cert_path: str = ""
    ssl_key_path: str = ""

    # Firewall
    allowed_subnets: List[str] = field(default_factory=lambda: [
        "192.168.0.0/16",   # Privatna mreža klasa C
        "10.0.0.0/8",       # Privatna mreža klasa A
        "172.16.0.0/12",    # Privatna mreža klasa B
        "100.64.0.0/10",    # Tailscale CGNAT
        "127.0.0.0/8",      # Localhost
    ])

    @property
    def lan_url(self) -> str:
        proto = "https" if self.ssl_enabled else "http"
        return f"{proto}://{self.mdns_name}:{self.api_port}"

    @property
    def tailscale_url(self) -> str:
        proto = "https" if self.ssl_enabled else "http"
        return f"{proto}://{self.tailscale_hostname}:{self.api_port}"

    @property
    def local_url(self) -> str:
        proto = "https" if self.ssl_enabled else "http"
        return f"{proto}://localhost:{self.api_port}"

    def is_allowed(self, ip: str) -> bool:
        """Provjeri je li IP adresa dopuštena."""
        try:
            addr = ipaddress.ip_address(ip)
            for subnet in self.allowed_subnets:
                if addr in ipaddress.ip_network(subnet):
                    return True
            return False
        except ValueError:
            return False


# ═══════════════════════════════════════════
# mDNS / BONJOUR DISCOVERY
# ═══════════════════════════════════════════

class ServiceDiscovery:
    """
    Automatsko otkrivanje Mac Studija na mreži.

    macOS nativno podržava Bonjour (mDNS/DNS-SD):
    - Mac Studio objavljuje servis "_nyx._tcp" na portu 8420
    - Djelatnikova računala automatski vide "nyx-studio.local"
    - Na Windowsu: Bonjour Print Services ili Tailscale

    Setup na Mac Studiju:
      dns-sd -R "Nyx Light" _http._tcp local 8420
    Ili koristi launchd plist (automatski).
    """

    @staticmethod
    def generate_bonjour_plist() -> str:
        """Generiraj macOS launchd plist za Bonjour advertising."""
        return """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>hr.nyxlight.bonjour</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/dns-sd</string>
        <string>-R</string>
        <string>Nyx Light Racunovodja</string>
        <string>_http._tcp</string>
        <string>local</string>
        <string>8420</string>
        <string>path=/</string>
        <string>version=3.0</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>"""

    @staticmethod
    def get_local_ips() -> List[Dict[str, str]]:
        """Dohvati sve lokalne IP adrese Mac Studija."""
        ips = []
        try:
            hostname = socket.gethostname()
            for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
                ip = info[4][0]
                if not ip.startswith("127."):
                    ips.append({"ip": ip, "hostname": hostname})
        except Exception:
            pass

        # Tailscale IP (100.x.x.x)
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
                ip = info[4][0]
                if ip.startswith("100."):
                    ips.append({"ip": ip, "type": "tailscale"})
        except Exception:
            pass

        return ips

    @staticmethod
    def detect_server(timeout: float = 2.0) -> Optional[Dict[str, Any]]:
        """Pokušaj pronaći Nyx Light server na mreži."""
        targets = [
            ("nyx-studio.local", 8420),
            ("nyx-studio", 8420),
            ("localhost", 8420),
        ]
        for host, port in targets:
            try:
                sock = socket.create_connection((host, port), timeout=timeout)
                sock.close()
                return {"host": host, "port": port, "url": f"http://{host}:{port}"}
            except (ConnectionRefusedError, socket.timeout, socket.gaierror, OSError):
                continue
        return None


# ═══════════════════════════════════════════
# ONBOARDING — UPUTA ZA NOVOG DJELATNIKA
# ═══════════════════════════════════════════

@dataclass
class EmployeeAccount:
    """Korisnički račun djelatnika."""
    username: str
    display_name: str
    role: str = "racunovoda"  # admin, racunovoda, pripravnik, readonly
    email: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    active: bool = True
    max_sessions: int = 2     # Koliko uređaja istovremeno
    permissions: List[str] = field(default_factory=lambda: [
        "chat", "view_invoices", "approve_entries", "rag_search",
    ])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "username": self.username,
            "display_name": self.display_name,
            "role": self.role,
            "active": self.active,
            "permissions": self.permissions,
        }


class OnboardingGuide:
    """
    Generira uputu za spajanje djelatnika.
    Admin pokrene ovo i pošalje djelatniku link/PDF.
    """

    ROLES = {
        "admin": {
            "name": "Administrator",
            "permissions": ["all"],
            "description": "Puni pristup sustavu, upravljanje korisnicima, SSH pristup",
        },
        "racunovoda": {
            "name": "Računovođa",
            "permissions": ["chat", "view_invoices", "approve_entries",
                           "rag_search", "reports", "clients"],
            "description": "Koristi AI chat, odobrava knjiženja, pretražuje zakone",
        },
        "pripravnik": {
            "name": "Pripravnik",
            "permissions": ["chat", "view_invoices", "rag_search"],
            "description": "Chat s AI-jem, pregled računa i zakona (ne može odobravati)",
        },
        "readonly": {
            "name": "Samo čitanje",
            "permissions": ["rag_search"],
            "description": "Može samo pretraživati zakone",
        },
    }

    @staticmethod
    def generate_quick_start(config: NetworkConfig = None,
                              username: str = "",
                              role: str = "racunovoda") -> str:
        """Generiraj quick start uputu za djelatnika."""
        config = config or NetworkConfig()
        role_info = OnboardingGuide.ROLES.get(role, OnboardingGuide.ROLES["racunovoda"])

        return f"""
╔══════════════════════════════════════════════════════════════╗
║           NYX LIGHT — UPUTA ZA BRZO SPAJANJE                ║
╚══════════════════════════════════════════════════════════════╝

Dobrodošli u Nyx Light — vaš AI asistent za računovodstvo!

═══ KORAK 1: OTVORITE PREGLEDNIK ═══

  U uredu (na WiFi ili Ethernetu):
    → {config.lan_url}

  Od kuće (s Tailscale-om):
    → {config.tailscale_url}

═══ KORAK 2: PRIJAVITE SE ═══

  Korisničko ime: {username or '[dodjeljuje administrator]'}
  Lozinka:        [dodjeljuje administrator]

  Vaša uloga: {role_info['name']}
  — {role_info['description']}

═══ KORAK 3: POČNITE RADITI ═══

  📊 Dashboard  — pregled dana (računi, anomalije, rokovi)
  💬 AI Chat    — pitajte AI o kontiranju, porezima, zakonima
  📥 Inbox      — primljeni i skenirani računi
  📋 Knjiženja  — pregledajte i odobrite AI prijedloge
  ⚖️ Zakoni     — pretražite zakone s vremenskim kontekstom

═══ VAŽNO ═══

  ✓ AI PREDLAŽE — VI ODOBRAVATE
    Ništa ne ide u CPP/Synesis bez vašeg klika "Odobri"

  ✓ SVE JE LOKALNO
    Vaši podaci nikad ne napuštaju ured (zero cloud)

  ✓ AI UČI IZ VAŠIH ISPRAVAKA
    Svaki put kad ispravite kontiranje, AI postaje pametniji

═══ POMOĆ ═══

  Ako ne možete pristupiti sustavu:
  1. Provjerite jeste li na uredskoj mreži (WiFi/Ethernet)
  2. Provjerite adresu: {config.lan_url}
  3. Obratite se administratoru

  Ako ste od kuće:
  1. Pokrenite Tailscale aplikaciju
  2. Otvorite: {config.tailscale_url}
"""

    @staticmethod
    def generate_tailscale_setup(os_type: str = "windows") -> str:
        """Uputa za instalaciju Tailscale-a."""
        guides = {
            "windows": """
TAILSCALE ZA WINDOWS
═══════════════════
1. Otvorite https://tailscale.com/download/windows
2. Preuzmite i instalirajte Tailscale
3. Kliknite "Log in" i prijavite se s Google/Microsoft računom
   (administrator vas mora pozvati na Tailscale mrežu)
4. Kad piše "Connected" — otvorite preglednik
5. Upišite: http://nyx-studio:8420
""",
            "mac": """
TAILSCALE ZA MAC
════════════════
1. Otvorite Mac App Store → traži "Tailscale"
2. Instalirajte i pokrenite
3. Kliknite ikonu u menu baru → "Log in"
4. Prijavite se (administrator vas mora pozvati)
5. Otvorite Safari: http://nyx-studio:8420
""",
            "iphone": """
TAILSCALE ZA iPHONE/iPAD
════════════════════════
1. App Store → traži "Tailscale"
2. Instalirajte i otvorite
3. Prijavite se → Dopustite VPN profil
4. U Safariju: http://nyx-studio:8420
""",
            "android": """
TAILSCALE ZA ANDROID
═══════════════════
1. Google Play → "Tailscale"
2. Instalirajte → prijavite se
3. U Chromeu: http://nyx-studio:8420
""",
        }
        return guides.get(os_type, guides["windows"])


# ═══════════════════════════════════════════
# FIREWALL & IP KONTROLA
# ═══════════════════════════════════════════

class AccessControl:
    """
    Kontrola pristupa na mrežnom nivou.

    Pravila:
    - Samo privatne mreže (192.168.x, 10.x, 172.16-31.x)
    - Tailscale (100.64.x.x)
    - Blokiraj sve javne IP adrese
    - MLX port (8422) samo localhost
    """

    def __init__(self, config: NetworkConfig = None):
        self.config = config or NetworkConfig()
        self._blocked_ips: set = set()
        self._access_log: List[Dict] = []

    def check_access(self, ip: str, port: int = 8420) -> Dict[str, Any]:
        """Provjeri pristup za danu IP adresu."""
        if ip in self._blocked_ips:
            self._log(ip, port, "BLOCKED")
            return {"allowed": False, "reason": "IP blocked"}

        if port == 8422 and ip != "127.0.0.1":
            self._log(ip, port, "DENIED_MLX")
            return {"allowed": False, "reason": "MLX port only accessible from localhost"}

        if not self.config.is_allowed(ip):
            self._log(ip, port, "DENIED_PUBLIC")
            return {"allowed": False, "reason": "Public IP not allowed"}

        method = self._detect_method(ip)
        self._log(ip, port, f"ALLOWED_{method.value.upper()}")
        return {"allowed": True, "method": method.value}

    def _detect_method(self, ip: str) -> AccessMethod:
        """Detektiraj način pristupa po IP-u."""
        if ip.startswith("127."):
            return AccessMethod.LOCALHOST
        if ip.startswith("100."):
            return AccessMethod.TAILSCALE
        return AccessMethod.LAN

    def block_ip(self, ip: str):
        self._blocked_ips.add(ip)

    def _log(self, ip: str, port: int, result: str):
        self._access_log.append({
            "timestamp": datetime.now().isoformat(),
            "ip": ip,
            "port": port,
            "result": result,
        })

    def get_stats(self) -> Dict[str, Any]:
        allowed = sum(1 for l in self._access_log if "ALLOWED" in l["result"])
        denied = sum(1 for l in self._access_log if "DENIED" in l["result"] or "BLOCKED" in l["result"])
        return {
            "total_checks": len(self._access_log),
            "allowed": allowed,
            "denied": denied,
            "blocked_ips": len(self._blocked_ips),
        }


# ═══════════════════════════════════════════
# CONNECTION STATUS DASHBOARD
# ═══════════════════════════════════════════

class ConnectionDashboard:
    """
    Real-time pregled spojenih djelatnika.
    Admin vidi tko je spojen, odakle, i što radi.
    """

    @dataclass
    class ConnectedUser:
        username: str
        ip: str
        access_method: AccessMethod
        connected_since: str
        last_activity: str
        current_page: str = "dashboard"
        ws_active: bool = False
        device: str = ""

        def to_dict(self):
            return {
                "username": self.username,
                "ip": self._mask_ip(),
                "method": self.access_method.value,
                "connected": self.connected_since,
                "page": self.current_page,
                "ws": self.ws_active,
                "device": self.device,
            }

        def _mask_ip(self) -> str:
            """Maskiraj IP za privatnost u dashboardu."""
            parts = self.ip.split(".")
            if len(parts) == 4:
                return f"{parts[0]}.{parts[1]}.*.{parts[3]}"
            return self.ip

    def __init__(self, max_users: int = 15):
        self.max_users = max_users
        self._users: Dict[str, "ConnectionDashboard.ConnectedUser"] = {}

    def connect(self, username: str, ip: str, device: str = "") -> bool:
        """Registriraj novog korisnika. Vrati False ako pun."""
        if username in self._users:
            self._users[username].last_activity = datetime.now().isoformat()
            return True
        if len(self._users) >= self.max_users:
            return False

        method = AccessMethod.TAILSCALE if ip.startswith("100.") else (
            AccessMethod.LOCALHOST if ip.startswith("127.") else AccessMethod.LAN)

        self._users[username] = self.ConnectedUser(
            username=username,
            ip=ip,
            access_method=method,
            connected_since=datetime.now().isoformat(),
            last_activity=datetime.now().isoformat(),
            device=device,
        )
        return True

    def disconnect(self, username: str):
        self._users.pop(username, None)

    def get_dashboard(self) -> Dict[str, Any]:
        by_method = {}
        for u in self._users.values():
            m = u.access_method.value
            by_method[m] = by_method.get(m, 0) + 1

        return {
            "connected": len(self._users),
            "max": self.max_users,
            "available": self.max_users - len(self._users),
            "by_method": by_method,
            "users": [u.to_dict() for u in self._users.values()],
        }


# ═══════════════════════════════════════════
# macOS NETWORK SETUP SCRIPTS
# ═══════════════════════════════════════════

class NetworkSetupGenerator:
    """Generira skripte za mrežni setup Mac Studija."""

    @staticmethod
    def generate_firewall_script() -> str:
        """macOS PF firewall konfiguracija."""
        return """#!/bin/bash
# Nyx Light — Firewall Setup
# Dozvoli samo privatne mreže na API port

echo "Konfiguracija macOS firewall-a za Nyx Light..."

# Dozvoli port 8420 samo s privatnih mreža
cat >> /etc/pf.conf << 'EOF'
# Nyx Light — Računovođa
pass in on en0 proto tcp from 192.168.0.0/16 to any port 8420
pass in on en0 proto tcp from 10.0.0.0/8 to any port 8420
pass in on en0 proto tcp from 172.16.0.0/12 to any port 8420
pass in on en0 proto tcp from 100.64.0.0/10 to any port 8420  # Tailscale
block in on en0 proto tcp from any to any port 8420            # Blokiraj ostalo

# MLX port — samo localhost
pass in on lo0 proto tcp from 127.0.0.1 to any port 8422
block in proto tcp from any to any port 8422
EOF

pfctl -f /etc/pf.conf
pfctl -e
echo "✅ Firewall konfiguriran"
"""

    @staticmethod
    def generate_static_ip_guide() -> str:
        """Uputa za postavljanje statičkog IP-a na Mac Studiju."""
        return """
POSTAVLJANJE STATIČKOG IP-A NA MAC STUDIJU
═══════════════════════════════════════════

1. System Settings → Network → Ethernet (ili Wi-Fi)
2. Details → TCP/IP
3. Configure IPv4: Manually
4. IP Address:    192.168.1.50    (ili slobodan IP u vašoj mreži)
   Subnet Mask:   255.255.255.0
   Router:        192.168.1.1     (vaš router)
5. DNS: 192.168.1.1, 1.1.1.1

ZAŠTO STATIČKI IP?
  Djelatnici mogu uvijek koristiti istu adresu:
  http://192.168.1.50:8420

ALTERNATIVA — mDNS (PREPORUČENO):
  Mac Studio automatski objavljuje "nyx-studio.local"
  → djelatnici koriste http://nyx-studio.local:8420
  → radi automatski, bez konfiguracije IP-a
  → na Windowsu treba Bonjour Print Services (besplatan)
"""

    @staticmethod
    def generate_router_dns_guide() -> str:
        """Uputa za DNS na uredskom routeru."""
        return """
DNS ZAPIS NA UREDSKOM ROUTERU (OPCIJSKI)
════════════════════════════════════════

Ako želite da djelatnici koriste "nyx" umjesto IP adrese:

1. Otvorite admin sučelje routera (obično 192.168.1.1)
2. Pronađite DNS / DHCP postavke
3. Dodajte statički DNS zapis:
     nyx-studio → 192.168.1.50  (IP Mac Studija)
4. Djelatnici sada mogu koristiti:
     http://nyx-studio:8420

ILI jednostavnije — koristite Tailscale:
  Svako računalo automatski vidi "nyx-studio" bez konfiguracije.
"""

    @staticmethod
    def generate_windows_hosts_entry() -> str:
        """Uputa za hosts file na Windowsu (ako nema mDNS)."""
        return """
WINDOWS: DODAVANJE nyx-studio U HOSTS FILE
═══════════════════════════════════════════

Ako Windows ne može riješiti "nyx-studio.local":

1. Pokrenite Notepad kao Administrator
2. Otvorite: C:\\Windows\\System32\\drivers\\etc\\hosts
3. Dodajte red na kraj:
     192.168.1.50    nyx-studio    nyx-studio.local
4. Spremite
5. Otvorite Chrome: http://nyx-studio:8420

BOLJA ALTERNATIVA:
  Instalirajte Tailscale → automatski radi bez hosts filea.
"""
